from datetime import datetime

import numpy as np
from loguru import logger

from chartrider.core.backtest.repository import BacktestRepository
from chartrider.core.common.broker.base import BaseBroker
from chartrider.core.common.repository.eventmonitor.monitor import EventMonitor
from chartrider.core.common.repository.models import (
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    TakerOrMaker,
    Timeframe,
)
from chartrider.utils.profiler import profile
from chartrider.utils.symbols import Symbol
from chartrider.utils.timeutils import TimeUtils


class BacktestBroker(BaseBroker):
    def __init__(self, repository: BacktestRepository, event_monitor: EventMonitor) -> None:
        super().__init__(repository, event_monitor)
        self.repository = repository

    @profile
    def next(self) -> None:
        """Handle orders processing and broker stuff."""
        for symbol in self.symbols:
            self.__process_orders(symbol)

        self.repository.next()
        self.equity_history[self.data_length - 1] = self.repository.fetch_balance().totalMarginBalance

    def prepare_initial_data(self, start: datetime, end: datetime) -> None:
        """Prepare data for each registered trading strategy within a given time period."""
        assert self._registered_strategies, "No strategies registered"
        prepended_duration = Timeframe.m1.milliseconds * self.max_candles_needed
        symbols = list(self.symbols)
        if len(symbols) > 1:
            self.repository.fetch_ohlcv_bulk(
                symbols=symbols,
                timeframe=Timeframe.m1,
                since=TimeUtils.timestamp_in_ms(start) - prepended_duration,
                until=TimeUtils.timestamp_in_ms(end),
            )
        else:
            self.repository.fetch_ohlcv(
                symbol=symbols[0],
                timeframe=Timeframe.m1,
                since=TimeUtils.timestamp_in_ms(start) - prepended_duration,
                until=TimeUtils.timestamp_in_ms(end),
            )

        self.equity_history = np.tile(np.nan, self.data_length)

    def set_length(self, length: int):
        self.candle_data.set_length(length)

        for strategy in self._registered_strategies.values():
            strategy.indicator_set_length(length)

    def get_last_ohlcv(self, symbol: Symbol) -> tuple[float, float, float, float, float, int]:
        return self.candle_data.ohlcv_last(symbol)

    async def close(self) -> None:
        await self.repository.close()

    # ------------------------------ Private Methods ----------------------------- #

    @profile
    def __process_orders(self, symbol: Symbol) -> None:
        """Process orders for a given symbol."""
        open, high, low, _, _, timestamp = self.get_last_ohlcv(symbol)

        for order in self.repository.fetch_open_orders(symbol):
            # check if order is still valid (e.g. it may have been cancelled in the previous iteration)
            if order.status != OrderStatus.open:
                continue

            # check if stop condition is met
            is_stop_hit = False
            if order.stopPrice is not None:
                if order.type == OrderType.stop_market or order.type == OrderType.stop:
                    if order.side.isBuy:
                        is_stop_hit = high >= order.stopPrice
                    else:  # order.side.isSell
                        is_stop_hit = low <= order.stopPrice
                elif order.type == OrderType.take_profit_market or order.type == OrderType.take_profit_market:
                    if order.side.isBuy:
                        is_stop_hit = low <= order.stopPrice
                    else:  # order.side.isSell
                        is_stop_hit = high >= order.stopPrice

                if not is_stop_hit:
                    continue

            is_executable, new_price, taker_or_maker = self.__check_order_executable(order, open, high, low)

            if is_stop_hit:
                # When the stop price is reached, a stop order becomes a market/limit order.
                if order.type == OrderType.stop_market or order.type == OrderType.take_profit_market:
                    order.type = OrderType.market
                elif order.type == OrderType.stop or order.type == OrderType.take_profit:
                    order.type = OrderType.limit
                # set stop price to None so that it is not checked again
                order.stopPrice = None

            if is_executable:
                assert new_price is not None and taker_or_maker is not None
                self.__execute_order(order, new_price, taker_or_maker, timestamp)

    def __check_order_executable(
        self, order: Order, open: float, high: float, low: float
    ) -> tuple[bool, float | None, TakerOrMaker | None]:
        """
        Check if an order is executable.
        Note that stop price is already hit at this point if it is a stop or take profit order.
        """
        is_buy = order.side == OrderSide.buy
        is_executed = False
        new_price = None
        taker_or_maker = None

        if (
            order.price is None
        ):  # order.type in [OrderType.market, OrderType.stop_market, OrderType.take_profit_market]
            is_executed = True
            if order.stopPrice is None:  # order.type == OrderType.market
                new_price = open
            else:
                if order.type == OrderType.stop_market:
                    new_price = max(open, order.stopPrice) if is_buy else min(open, order.stopPrice)
                else:  # order.type == OrderType.take_profit_market
                    new_price = min(open, order.stopPrice) if is_buy else max(open, order.stopPrice)
            taker_or_maker = TakerOrMaker.taker

        else:  # order.type in [OrderType.limit, OrderType.stop, OrderType.take_profit]
            is_executed = low < order.price if is_buy else high > order.price
            if not is_executed:
                return is_executed, None, None

            if order.stopPrice is None:  # order.type == OrderType.limit
                new_price = min(open, order.price) if is_buy else max(open, order.price)
                is_taker = open <= order.price if is_buy else open >= order.price
            else:
                # When stop and limit are hit within the same candle, should we fill the order?
                # For now, we will fill the order assuming the stop price is hit first.
                logger.warning(
                    "Stop and limit hit within the same candle. Filling order assuming stop price is hit first."
                )
                if (order.stopPrice > order.price and is_buy) or (order.stopPrice < order.price and not is_buy):
                    new_price = order.price
                    is_taker = False
                else:
                    if order.type == OrderType.stop:
                        new_price = max(open, order.stopPrice) if is_buy else min(open, order.stopPrice)
                    else:  # order.type == OrderType.take_profit
                        new_price = min(open, order.stopPrice) if is_buy else max(open, order.stopPrice)
                    is_taker = True
            taker_or_maker = TakerOrMaker.taker if is_taker else TakerOrMaker.maker

        return is_executed, new_price, taker_or_maker

    def __execute_order(self, order: Order, new_price: float, taker_or_maker: TakerOrMaker, timestamp: int) -> None:
        """
        Execute an order.
        """
        trade = self.repository.open_trade(
            price=new_price,
            timestamp=timestamp,
            order=order,
            taker_or_maker=taker_or_maker,
        )

        if trade is None:
            return

        if order.clientOrderId is None:
            logger.warning(
                "Order has no clientOrderId. Cannot update strategy accordingly. "
                "This will cause inconsistency in the strategy's internal state."
            )
            return


if __name__ == "__main__":
    pass
