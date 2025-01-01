import asyncio
from functools import cache
from typing import Any, Iterable, List, cast

import ccxt as ccxt
from ccxt.base.errors import ExchangeError, OrderNotFound
from loguru import logger

from chartrider.core.common.repository.base import BaseRepository
from chartrider.core.common.repository.candle.repository import (
    BaseCandleRepository,
    CandleRepository,
)
from chartrider.core.common.repository.contingent.repository import (
    ContingentInfoBaseRepository,
    ContingentInfoDBRepository,
    ContingentInfoDto,
)
from chartrider.core.common.repository.eventmonitor.monitor import EventMonitor
from chartrider.core.common.repository.models import (
    Balance,
    ClientOrderId,
    ContingentOrder,
    MarginMode,
    Order,
    OrderAction,
    OrderBook,
    OrderRequestParams,
    OrderStatus,
    OrderType,
    Position,
    PositionSide,
    Timeframe,
    TimeInForce,
    Trade,
)
from chartrider.utils.eventloop import AsyncEventLoop
from chartrider.utils.exchange import ExchangeFactory
from chartrider.utils.secrets import SecretStore
from chartrider.utils.symbols import Symbol
from chartrider.utils.timeutils import Timestamp, TimeUtils


class LiveRepository(BaseRepository):
    def __init__(
        self,
        exchange: ccxt.binanceusdm,
        candle_repository: BaseCandleRepository,
        contingent_info_repository: ContingentInfoBaseRepository,
        event_monitor: EventMonitor,
    ) -> None:
        super().__init__()
        self.binance: ccxt.binanceusdm = exchange
        self.event_loop = AsyncEventLoop().start_loop()
        self.candle_repository = candle_repository
        self.__event_monitor = event_monitor
        self.__contingent_repository = contingent_info_repository

    def watch_candles(self, symbol: Symbol, timeframe: Timeframe) -> None:
        self.event_loop.add_task(self.candle_repository.download_realtime_candle_data(symbol, timeframe))

    def watch_events(self) -> None:
        self.event_loop.add_task(self.__event_monitor.watch_orders(main_loop=self.event_loop.loop))

    def fetch_balance(self) -> Balance:
        data = self.binance.fetch_balance()
        data = cast(dict[str, Any], data)
        return Balance(**data["info"], info=data["info"])

    def fetch_order(self, order: Order) -> Order | None:
        fetched_order = self.__fetch_order_from_id(order.id, order.symbol)
        if fetched_order is None:
            return None
        if fetched_order.status == "closed":
            fetched_order.trades = self.fetch_order_trades(order)
        return fetched_order

    def fetch_orders(self, symbol: Symbol) -> list[Order]:
        data: list[Any] = self.binance.fetch_orders(symbol)
        return [Order(**order) for order in data]

    def fetch_open_orders(self, symbol: Symbol) -> list[Order]:
        data: list[Any] = self.binance.fetch_open_orders(symbol)
        return [Order(**order) for order in data]

    def fetch_closed_orders(self, symbol: Symbol) -> list[Order]:
        data = self.binance.fetch_closed_orders(symbol)
        return [Order(**order) for order in data]

    def fetch_trades(self, symbol: Symbol) -> list[Trade]:
        data: list[Any] = self.binance.fetch_my_trades(symbol)
        return [Trade(**trade) for trade in data]

    def fetch_order_trades(self, order: Order) -> list[Trade]:
        data: list[Any] = self.binance.fetch_my_trades(order.symbol, params={"orderId": order.id})
        return [Trade(**trade) for trade in data]

    def fetch_order_book(self, symbol: Symbol) -> OrderBook:
        data = self.binance.fetch_order_book(symbol)
        return OrderBook(**data)

    def fetch_ohlcv(self, symbol: Symbol, timeframe: Timeframe, since: Timestamp, until: Timestamp | None) -> None:
        data = self.candle_repository.fetch_candle_data(
            symbol,
            start=since,
            end=until or TimeUtils.timestamp_in_ms(),
            timeframe=timeframe,
        )
        self.candle_data.combine(data)

    def fetch_ohlcv_bulk(
        self, symbols: List[Symbol], timeframe: Timeframe, since: Timestamp, until: Timestamp | None
    ) -> None:
        data = self.candle_repository.fetch_candle_data_bulk(
            symbols,
            start=since,
            end=until or TimeUtils.timestamp_in_ms(),
            timeframe=timeframe,
        )

        for _, symbol_data in data.items():
            self.candle_data.combine(symbol_data)

    def update_latest_ohlcv(self, symbol: Symbol, timeframe: Timeframe, limit: int):
        """
        A more efficient version of `fetch_ohlcv` that only fetches the latest candles.
        """
        data = self.candle_repository.fetch_recent_candle_data(symbol, limit, timeframe=timeframe)
        self.candle_data.combine(data)

    def enable_hedge_mode(self):
        try:
            self.binance.set_position_mode(hedged=True)
        except ExchangeError:
            pass

    def fetch_positions(self, symbols: Iterable[str]) -> list[Position]:
        symbols = list(symbols)
        assert len(symbols) > 0
        data = self.binance.fetch_positions(symbols)
        return [Position(**position) for position in data if position["contracts"] > 0]

    def get_last_price(self, symbol: Symbol) -> float:
        last_timestamp_saved = self.candle_data.timestamp_last
        current_timestamp = TimeUtils.round_down_to_timeframe(TimeUtils.timestamp_in_ms(), Timeframe.m1)

        if last_timestamp_saved + Timeframe.m1.milliseconds < current_timestamp:
            logger.warning(
                f"Using outdated data for {symbol}. "
                f"Current timestamp is {current_timestamp} but last saved timestamp is {last_timestamp_saved}."
            )
        return self.candle_data.close[symbol][-1]

    def next(self):
        contingent_infos = self.__contingent_repository.get_pending_contingent_infos()
        for info in contingent_infos:
            self.__trigger_contingent_if_needed(info)

    def is_liquidated_by_contingent(self, order: Order) -> bool:
        return self.__contingent_repository.is_liquidated_by_contingent(order.id, order.symbol)

    def create_order(
        self,
        symbol: Symbol,
        action: OrderAction,
        amount: float,
        price: float | None,
        contingent_sl: ContingentOrder | None = None,
        contingent_tp: ContingentOrder | None = None,
        stop_price: float | None = None,
        time_in_force: TimeInForce = TimeInForce.GTC,
        client_order_id: ClientOrderId | None = None,
    ) -> Order | None:
        if action.isClosing:
            assert contingent_sl is None and contingent_tp is None, "Closing orders cannot have contingent orders."

        additional_params = OrderRequestParams()
        additional_params.stopPrice = stop_price
        additional_params.positionSide = action.positionSide
        additional_params.clientOrderId = client_order_id

        last_price = None
        if stop_price is not None:
            # fetch last price to determine if order is a stop or take profit
            last_price = self.get_last_price(symbol)

        if (
            type := self.get_order_type(action, price=price, stop_price=stop_price, last_price=last_price)
        ) != OrderType.market:
            additional_params.timeInForce = time_in_force.value

        try:
            data = self.binance.create_order(
                symbol,
                type,  # type: ignore
                action.orderSide,  # type: ignore
                amount,
                price,
                params=additional_params.model_dump(exclude_none=True),
            )
        except ExchangeError as e:
            logger.error(e)
            return None

        created_order = Order(**data)

        if action.isOpening:
            self.__contingent_repository.create_contingent_info(
                order_id=created_order.id,
                side=created_order.positionSide,
                symbol=created_order.symbol,
                contingent_sl=contingent_sl,
                contingent_tp=contingent_tp,
            )

        logger.info(f"Order {created_order.id} was created.\n{created_order.format(html=True)}\n")
        return created_order

    def cancel_order(self, order: Order) -> Order | None:
        try:
            data = self.binance.cancel_order(order.id, order.symbol)
            self.__contingent_repository.delete_contingent_info(order.id, order.symbol)
            logger.info(f"Canceled order {order.id} ({order.symbol}) and its contingent information.")
        except OrderNotFound:
            return None
        return Order(**data)

    def cancel_all_orders(self, symbol: Symbol) -> None:
        self.binance.cancel_all_orders(symbol)
        self.__contingent_repository.delete_pending_contingent_infos(symbol, side=PositionSide.long)
        self.__contingent_repository.delete_pending_contingent_infos(symbol, side=PositionSide.short)
        logger.info(f"Canceled all open orders for symbol {symbol}.")

    def cancel_contingent_orders(self, original_order: Order) -> None:
        self.__contingent_repository.delete_contingent_info(original_order.id, original_order.symbol)
        logger.info(f"Canceled contingent orders for order {original_order.id} ({original_order.symbol}).")

    def close_position(self, position: Position):
        self.create_order(
            symbol=position.symbol,
            action=OrderAction.close_long if position.side.isLong else OrderAction.close_short,
            amount=position.contracts,
            price=None,
            client_order_id=ClientOrderId(strategy=None, timestamp=TimeUtils.timestamp_in_ms()),
        )

    def set_leverage(self, symbol: Symbol, leverage: int):
        self.binance.set_leverage(leverage, symbol=symbol)
        logger.info(f"Leverage for {symbol} set to {leverage}.")
        self.get_leverage.cache_clear()

    @cache
    def get_leverage(self, symbol: Symbol) -> int:
        positions = self.fetch_positions([symbol])
        assert len(positions) > 0
        return positions[0].leverage

    def set_margin_mode(self, symbol: Symbol, margin_mode: MarginMode):
        self.binance.set_margin_mode(margin_mode, symbol=symbol)

    async def close(self):
        self.event_loop.stop_loop()
        await self.candle_repository.close()

    # ------------------------------ Private Methods ----------------------------- #

    def __fetch_order_from_id(self, order_id: str, symbol: Symbol) -> Order | None:
        try:
            data = self.binance.fetch_order(order_id, symbol=symbol)
        except OrderNotFound:
            return None
        return Order(**data)

    def __trigger_contingent_if_needed(self, info: ContingentInfoDto):
        last_price = self.get_last_price(info.symbol)

        trigger = False
        execute_price = None

        if info.sl_trigger_price is not None and (
            info.sl_trigger_price >= last_price if info.side.isLong else info.sl_trigger_price <= last_price
        ):
            trigger = True
            execute_price = info.sl_execute_price
        elif info.tp_trigger_price is not None and (
            info.tp_trigger_price <= last_price if info.side.isLong else info.tp_trigger_price >= last_price
        ):
            trigger = True
            execute_price = info.tp_execute_price

        if not trigger:
            return

        order = self.__fetch_order_from_id(info.order_id, info.symbol)

        if order is None:
            self.__contingent_repository.delete_contingent_info(info.order_id, info.symbol)
            logger.warning(f"Order {info.order_id} was not found. Deleted contingent info.")
            return

        if order.status != OrderStatus.closed:
            return

        if not isinstance(order.clientOrderId, ClientOrderId):
            self.__contingent_repository.delete_contingent_info(info.order_id, info.symbol)
            logger.warning(f"Order {order.id} does not have a client order id. Deleted contingent info.")
            return

        self.create_order(
            symbol=info.symbol,
            action=OrderAction.close_long if order.positionSide.isLong else OrderAction.close_short,
            amount=order.amount,
            price=execute_price,
            client_order_id=ClientOrderId(
                strategy=order.clientOrderId.strategy, timestamp=TimeUtils.timestamp_in_ms()
            ),
        )

        self.__event_monitor.did_liquidate_by_contingent.publish(order.id)
        self.__contingent_repository.mark_contingent_info_as_triggered(info.order_id, info.symbol)
        logger.info(f"Contingent Order {order.id} was successfully triggered.")


if __name__ == "__main__":
    import time

    from chartrider.core.common.repository.candle.repository import (
        CandleAPIRepository,
        CandleDBRepository,
    )
    from chartrider.database.connection import DBSessionFactory

    __testnet = False
    session_factory = DBSessionFactory()
    secret_store = SecretStore(from_telegram=False)
    secret = secret_store.get_secret(__testnet)
    assert secret is not None
    exchange_factory = ExchangeFactory(secret_store)
    candle_db_repository = CandleDBRepository(session_factory=session_factory)
    candle_api_repository = CandleAPIRepository(
        exchange=exchange_factory.get_public_exchange(__testnet),
        async_exchange=exchange_factory.get_async_exchange(__testnet),
    )
    candle_repository = CandleRepository(db_repository=candle_db_repository, api_repository=candle_api_repository)
    contingent_repository = ContingentInfoDBRepository(
        session_factory=session_factory, testnet=__testnet, user_id=secret.hash()
    )
    event_monitor = EventMonitor(exchange=exchange_factory.get_async_exchange(__testnet))
    live_repository = LiveRepository(
        exchange=exchange_factory.get_exchange(__testnet),
        candle_repository=candle_repository,
        contingent_info_repository=contingent_repository,
        event_monitor=event_monitor,
    )

    try:
        live_repository.watch_events()
        time.sleep(1000)
    finally:
        asyncio.run(live_repository.close())
