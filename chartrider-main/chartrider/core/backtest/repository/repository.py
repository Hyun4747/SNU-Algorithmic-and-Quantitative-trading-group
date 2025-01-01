import itertools
import uuid
from collections import defaultdict
from functools import cache
from typing import Iterable, List

from loguru import logger

from chartrider.core.common.repository.base import BaseRepository
from chartrider.core.common.repository.candle.repository import BaseCandleRepository
from chartrider.core.common.repository.contingent.repository import (
    ContingentInfoBaseRepository,
    ContingentInfoDto,
)
from chartrider.core.common.repository.eventmonitor.monitor import EventMonitor
from chartrider.core.common.repository.models import (
    Balance,
    ClientOrderId,
    ContingentOrder,
    Fee,
    MarginMode,
    Order,
    OrderAction,
    OrderStatus,
    OrderType,
    Position,
    PositionSide,
    TakerOrMaker,
    Timeframe,
    TimeInForce,
    Trade,
)
from chartrider.settings import settings
from chartrider.utils.exceptions import InvalidOrder, InvalidTrade, OutOfMoney
from chartrider.utils.profiler import profile
from chartrider.utils.symbols import Symbol
from chartrider.utils.timeutils import Timestamp, TimeUtils


class BacktestRepository(BaseRepository):
    def __init__(
        self,
        initial_balance: Balance,
        candle_repository: BaseCandleRepository,
        contingent_info_repository: ContingentInfoBaseRepository,
        event_monitor: EventMonitor,
    ) -> None:
        super().__init__()
        self.__balance = initial_balance
        self.__orders: dict[str, dict[tuple[Symbol, PositionSide], list[Order]]] = defaultdict(
            lambda: defaultdict(list)
        )  # outer key: status, inner key: (symbol, side)
        self.__trades: list[Trade] = []
        self.__leverage: dict[Symbol, int] = defaultdict(lambda: 1)
        self.__marginMode: MarginMode = MarginMode.isolated
        self.__open_positions: dict[tuple[Symbol, PositionSide], Position] = dict()  # (symbol, side) -> position
        self.__closed_positions: dict[tuple[Symbol, PositionSide], list[Position]] = defaultdict(list)
        self.__candle_repository = candle_repository
        self.__event_monitor = event_monitor
        self.contingent_repository = contingent_info_repository

    def set_leverage(self, symbol: Symbol, leverage: int) -> None:
        assert leverage >= 1
        assert (symbol, PositionSide.long) not in self.__open_positions
        assert (symbol, PositionSide.short) not in self.__open_positions
        self.__leverage[symbol] = leverage

    def get_leverage(self, symbol: Symbol) -> int:
        return self.__leverage[symbol]

    def set_margin_mode(self, symbol: Symbol, margin_mode: MarginMode):
        assert (symbol, PositionSide.long) not in self.__open_positions
        assert (symbol, PositionSide.short) not in self.__open_positions
        self.__marginMode = margin_mode

    def fetch_balance(self) -> Balance:
        return self.__balance

    def fetch_order(self, order: Order) -> Order | None:
        return self.__fetch_order_from_id(order.id, order.symbol)

    def fetch_orders(self, symbol: Symbol, position_side: PositionSide | None = None) -> list[Order]:
        sides = [position_side] if position_side is not None else [PositionSide.long, PositionSide.short]
        return list(
            itertools.chain(*[self.__orders[status][(symbol, side)] for status in self.__orders for side in sides])
        )

    def fetch_closed_orders(self, symbol: Symbol, position_side: PositionSide | None = None) -> list[Order]:
        sides = [position_side] if position_side is not None else [PositionSide.long, PositionSide.short]
        return list(itertools.chain(*[self.__orders[OrderStatus.closed][(symbol, side)] for side in sides]))

    @profile
    def fetch_open_orders(
        self, symbol: Symbol | None = None, position_side: PositionSide | None = None
    ) -> list[Order]:
        sides = [position_side] if position_side is not None else [PositionSide.long, PositionSide.short]
        if symbol is not None:
            return list(itertools.chain(*[self.__orders[OrderStatus.open][(symbol, side)] for side in sides]))
        else:
            return list(
                itertools.chain(
                    *[
                        self.__orders[OrderStatus.open][key]
                        for key in self.__orders[OrderStatus.open]
                        if key[1] in sides
                    ]
                )
            )

    def fetch_trades(self, symbol: Symbol | None = None) -> list[Trade]:
        return [trade for trade in self.__trades if symbol is None or trade.symbol == symbol]

    def fetch_positions(self, symbols: Iterable[Symbol], position_side: PositionSide | None = None) -> list[Position]:
        return sorted(
            [
                position
                for position in self.__open_positions.values()
                if position.symbol in symbols and (position_side is None or position.side == position_side)
            ],
            key=lambda x: x.timestamp,
        )

    def fetch_ohlcv(self, symbol: Symbol, timeframe: Timeframe, since: Timestamp, until: Timestamp | None) -> None:
        assert until is not None
        data = self.__candle_repository.fetch_candle_data(
            symbol,
            start=since,
            end=until,
            timeframe=timeframe,
        )
        self.candle_data.combine(data)

    def fetch_ohlcv_bulk(
        self, symbols: List[Symbol], timeframe: Timeframe, since: Timestamp, until: Timestamp | None
    ) -> None:
        assert until is not None

        data = self.__candle_repository.fetch_candle_data_bulk(
            symbols,
            start=since,
            end=until,
            timeframe=timeframe,
        )

        for symbol, candle_data in data.items():
            self.candle_data.combine(candle_data)

    @profile
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
        last_price = self.get_last_price(symbol)
        timestamp = self.get_next_timestamp()

        order_type = self.get_order_type(action=action, price=price, stop_price=stop_price, last_price=last_price)

        # create order instance
        order = Order(
            id=str(uuid.uuid4()),
            clientOrderId=client_order_id,
            symbol=symbol,
            side=action.orderSide,
            amount=amount,
            price=price,
            stopPrice=stop_price,
            type=order_type,
            timeInForce=time_in_force,
            timestamp=timestamp,
            status=OrderStatus.open,
            filled=0,
            trades=[],
            info=dict(positionSide=action.positionSide),  # to mimic live data
        )

        # Check if the prices of the order is valid
        # Note that for invalid order, this validation raises the error rather than returning None,
        # because the prices are set by the user.
        self.__validate_price(order, contingent_sl=contingent_sl, contingent_tp=contingent_tp)

        try:
            # Check if the order is valid w.r.t. exchange rules
            order = order.validated()
        except InvalidOrder as e:
            logger.warning(f"Order rejected due to error: {e}")
            self.__update_open_order_status(order, OrderStatus.rejected)
            return None

        if order.orderAction.isOpening:
            # Check if there's enough money to open a position
            estimated_total_cost = (
                ((price or last_price) / self.get_leverage(symbol)) * order.amount * (1 + self.get_max_fee_rate())
            )
            if estimated_total_cost > self.__balance.availableBalance:
                logger.warning("Not enough money to open an order.")
                self.__update_open_order_status(order, OrderStatus.rejected)
                return None
        elif order.orderAction.isClosing:
            # Check if there's an open position to close
            if (position := self.__get_open_position(order.symbol, order.positionSide)) is None:
                logger.warning("No open position to close.")
                self.__update_open_order_status(order, OrderStatus.rejected)
                return None
            if order.amount > position.contracts:
                logger.warning(f"Order amount {order.amount} exceeds position contracts {position.contracts}.")
                order.amount = min(order.amount, position.contracts)  # adjust order amount using reduce-only rules

        if order.orderAction.isOpening and (contingent_sl is not None or contingent_tp is not None):
            self.contingent_repository.create_contingent_info(
                order_id=order.id,
                symbol=order.symbol,
                side=order.positionSide,
                contingent_sl=contingent_sl,
                contingent_tp=contingent_tp,
            )

        self.__update_open_order_status(order, OrderStatus.open)
        return order

    def cancel_order(self, order: Order) -> Order | None:
        if order.status == OrderStatus.canceled:
            logger.warning(f"Order {order.id} is already canceled.")
            return None
        return self.__update_open_order_status(order, OrderStatus.canceled)

    def cancel_all_orders(self, symbol: Symbol, position_side: PositionSide | None = None) -> None:
        for order in self.fetch_open_orders(symbol, position_side):
            self.cancel_order(order)

    def cancel_contingent_orders(self, original_order: Order) -> None:
        self.contingent_repository.delete_contingent_info(original_order.id, original_order.symbol)

    @profile
    def next(self) -> None:
        """
        Update the mark price of all open positions on every start of a new candle.
        This ensures that `Position.markPrice` is always up-to-date."""
        for position in list(self.__open_positions.values()):
            self.__liquidate_position_if_needed(position)
            position.markPrice = self.get_last_price(position.symbol)

        self.__update_balance()
        contingent_infos = self.contingent_repository.get_pending_contingent_infos()
        for info in contingent_infos:
            self.__trigger_contingent_if_needed(info)

    def is_liquidated_by_contingent(self, order: Order) -> bool:
        return self.contingent_repository.is_liquidated_by_contingent(order.id, order.symbol)

    async def close(self):
        await self.__candle_repository.close()

    # ------------------------- Backtesting-Only Methods ------------------------- #

    def fetch_closed_positions(self) -> list[Position]:
        return sorted(
            list(itertools.chain(*[positions_list for positions_list in self.__closed_positions.values()])),
            key=lambda x: x.timestamp,
        )

    @profile
    def open_trade(
        self,
        price: float,
        timestamp: int,
        order: Order,
        taker_or_maker: TakerOrMaker,
    ) -> Trade | None:
        notional_value = price * order.amount
        fee_rate = self.get_fee_rate(taker_or_maker)
        fee = Fee(
            currency=settings.stake_currency,
            cost=notional_value * fee_rate,
            rate=fee_rate,
        )
        estimated_total_cost = notional_value / self.get_leverage(order.symbol) + fee.cost
        trade = Trade(
            id=str(uuid.uuid4()),
            timestamp=timestamp,
            symbol=order.symbol,
            order=order.id,
            side=order.side,
            takerOrMaker=taker_or_maker,
            price=price,
            amount=order.amount,
            fee=fee,
        )

        try:
            # Check if the trade is valid w.r.t. exchange rules
            trade = trade.validated()
        except InvalidTrade as e:
            logger.error(
                f"Trade couldn't be validated due to error: {e}. "
                "This issue may indicate a potential bug or inconsistency in the backtest repository "
            )
            raise e

        if order.orderAction.isOpening:
            self.__update_open_order_status(order, OrderStatus.closed)
            # Check if there's enough money to open a position
            if estimated_total_cost > self.__balance.availableBalance:
                raise OutOfMoney
        if order.orderAction.isClosing:
            # Check if there's an open position to close
            position = self.__get_open_position(order.symbol, order.positionSide)
            if position is None:
                # This could happen if the position has already been liquidated by the system
                self.__update_open_order_status(order, OrderStatus.canceled)
                return
            self.__update_open_order_status(order, OrderStatus.closed)
            assert order.amount <= position.contracts

        order.trades.append(trade)
        self.__trades.append(trade)
        self.__update_position(trade, order.orderAction)
        self.__balance.totalWalletBalance -= fee.cost
        self.__event_monitor.did_close.publish(order.id)
        return trade

    def get_last_price(self, symbol: Symbol) -> float:
        return self.candle_data.close[symbol][-1]

    @cache
    def get_fee_rate(self, taker_or_maker: TakerOrMaker) -> float:
        if taker_or_maker == TakerOrMaker.taker:
            return 0.0006
        else:
            return 0.0003

    @cache
    def get_max_fee_rate(self) -> float:
        return max(self.get_fee_rate(TakerOrMaker.taker), self.get_fee_rate(TakerOrMaker.maker))

    # ------------------------------ Private Methods ----------------------------- #

    def __fetch_order_from_id(self, order_id: str, symbol: Symbol) -> Order | None:
        for order in self.fetch_orders(symbol):
            if order.id == order_id:
                return order
        return None

    def __trigger_contingent_if_needed(self, info: ContingentInfoDto):
        low, high = self.get_last_low_high(info.symbol)

        trigger = False
        execute_price = None

        if info.sl_trigger_price is not None and (
            low <= info.sl_trigger_price if info.side.isLong else info.sl_trigger_price <= high
        ):
            trigger = True
            execute_price = info.sl_execute_price
        elif info.tp_trigger_price is not None and (
            info.tp_trigger_price <= high if info.side.isLong else low <= info.tp_trigger_price
        ):
            trigger = True
            execute_price = info.tp_execute_price

        if not trigger:
            return

        order = self.__fetch_order_from_id(info.order_id, info.symbol)
        assert order is not None, "Order should not be None at this point."
        if order.status != OrderStatus.closed:
            return

        self.create_order(
            symbol=info.symbol,
            action=OrderAction.close_long if order.positionSide.isLong else OrderAction.close_short,
            amount=order.amount,
            price=execute_price,
            client_order_id=(
                ClientOrderId(strategy=order.clientOrderId.strategy, timestamp=self.get_next_timestamp())
                if isinstance(order.clientOrderId, ClientOrderId)
                else None
            ),
        )

        self.__event_monitor.did_liquidate_by_contingent.publish(info.order_id)

        logger.info(f"Contingent Order {order.id} was successfully triggered.")
        self.contingent_repository.mark_contingent_info_as_triggered(info.order_id, info.symbol)

        if (signposter := order.signposter) is not None:
            signposter.end_interval(
                signpost_id=info.order_id,
                symbol=info.symbol,
                name=f"Contingent Order for {order.id}",
                description=f"{execute_price=} {order.amount=}",
                timestamp=self.get_next_timestamp(),
            )

    def __liquidate_position(self, position: Position) -> None:
        logger.warning(
            f"Liquidating position of {position.symbol} due to current price {self.get_last_price(position.symbol)} "
            f"reaching the liquidation price of {position.liquidationPrice}"
        )
        order = self.create_order(
            symbol=position.symbol,
            action=OrderAction.close_long if position.side.isLong else OrderAction.close_short,
            amount=position.contracts,
            price=None,
            client_order_id=ClientOrderId(strategy=None, timestamp=TimeUtils.timestamp_in_ms()),
        )
        assert order is not None, "Force liquidation failed. The exchange just made a loss."
        self.contingent_repository.delete_pending_contingent_infos(symbol=position.symbol, side=position.side)
        self.__event_monitor.did_force_liquidate.publish(liquidation_order=order)

    def __liquidate_position_if_needed(self, position: Position) -> None:
        if position.side.isLong and self.get_leverage(position.symbol) == 1:
            # Optimization: skip checking liquidation price if leverage is 1
            return
        low, high = self.get_last_low_high(position.symbol)
        if position.side.isLong and low <= position.liquidationPrice:
            self.__liquidate_position(position)
            return
        if position.side.isShort and high >= position.liquidationPrice:
            self.__liquidate_position(position)
            return

    def get_last_low_high(self, symbol: Symbol) -> tuple[float, float]:
        return self.candle_data.low[symbol][-1], self.candle_data.high[symbol][-1]

    def get_next_timestamp(self) -> int:
        return self.candle_data.timestamp_next

    @profile
    def __update_open_order_status(self, order: Order, new_status: OrderStatus) -> Order:
        assert order.status == OrderStatus.open, "Only open orders can be updated."

        match new_status:
            case OrderStatus.open:
                pass
            case OrderStatus.rejected:
                assert order not in self.__orders[OrderStatus.open][(order.symbol, order.positionSide)]
                order.status = new_status
            case _:  # closed, canceled or expired
                assert order in self.__orders[OrderStatus.open][(order.symbol, order.positionSide)]
                self.__orders[OrderStatus.open][(order.symbol, order.positionSide)].remove(order)
                order.status = new_status

                if new_status == OrderStatus.canceled:
                    self.cancel_contingent_orders(order)

                if new_status == OrderStatus.closed:
                    order.filled = order.amount

        self.__orders[new_status][(order.symbol, order.positionSide)].append(order)
        self.__update_balance()
        return order

    @profile
    def __update_position(self, trade: Trade, action: OrderAction):
        key = (trade.symbol, action.positionSide)
        last_price = self.get_last_price(trade.symbol)
        leverage = self.get_leverage(trade.symbol)

        isolated_wallet = (
            trade.price * trade.amount / leverage - trade.fee.cost if self.__marginMode == MarginMode.isolated else 0
        )

        if key not in self.__open_positions:
            self.__open_positions[key] = Position(
                symbol=trade.symbol,
                timestamp=trade.timestamp,
                hedged=True,
                side=action.positionSide,
                contracts=trade.amount,
                openedAmount=trade.amount,
                entryPrice=trade.price,
                markPrice=last_price,
                leverage=leverage,
                marginMode=self.__marginMode,
                averageOpenPrice=trade.price,
                isolatedWallet=isolated_wallet,
            )
            self.__update_balance()
            return

        position = self.__open_positions[key]
        if action.isOpening:
            assert position.openedAmount is not None and position.averageOpenPrice is not None
            new_opened_amount = position.openedAmount + trade.amount
            # We need to round the contracts to avoid floating point errors when comparing with 0
            new_total_contracts = round(position.contracts + trade.amount, 8)

            # Update the entry price using a weighted average
            position.entryPrice = (
                position.entryPrice * position.contracts + trade.price * trade.amount
            ) / new_total_contracts

            position.averageOpenPrice = (
                position.averageOpenPrice * position.openedAmount + trade.price * trade.amount
            ) / new_opened_amount
            position.openedAmount = new_opened_amount
            position.contracts = new_total_contracts
            if position.marginMode.isIsolated:
                position.isolatedWallet += isolated_wallet
        elif action.isClosing:
            new_closed_amount = position.closedAmount + trade.amount

            if position.averageClosePrice is None:
                # Set the average close price to the price of the first trade
                position.averageClosePrice = trade.price
            else:
                # Update the average close price using a weighted average
                position.averageClosePrice = (
                    position.averageClosePrice * position.closedAmount + trade.price * trade.amount
                ) / new_closed_amount

            # Calculate realized PnL for the closed portion
            realized_pnl = (trade.price - position.entryPrice) * trade.amount
            realized_pnl *= 1 if position.side == PositionSide.long else -1

            # Update the realized Pnl of the trade
            trade.realizedPnl = realized_pnl
            trade.realizedPnlPercent = (realized_pnl / (position.entryPrice * trade.amount)) * 100

            # Update wallet balance with realized PnL for the closed portion
            self.__balance.totalWalletBalance += realized_pnl

            position.closedAmount = new_closed_amount

            if position.marginMode.isIsolated:
                # Decrease the isolated wallet according to the ratio of the closed amount to the total amount
                position.isolatedWallet -= (trade.amount / position.contracts) * position.isolatedWallet

            position.contracts = round(position.contracts - trade.amount, 8)

            if position.contracts == 0:
                assert position.isolatedWallet == 0, "Isolated wallet can't be 0 when contracts are 0"
                position.closedTimestamp = trade.timestamp
                del self.__open_positions[key]
                self.__closed_positions[key].append(position)
                self.__cancel_all_closing_orders(closing_position=position)
                self.contingent_repository.delete_pending_contingent_infos(symbol=position.symbol, side=position.side)

        self.__update_balance()

    def __cancel_all_closing_orders(self, closing_position: Position):
        """
        In Binance, when a position is closed, all the open orders trying to close the position
        are automatically canceled.
        """
        for order in self.fetch_open_orders(closing_position.symbol, closing_position.side):
            if order.orderAction.isClosing:
                self.__update_open_order_status(order, OrderStatus.canceled)

    @profile
    def __update_balance(self):
        """
        Update the balances of the account as a result of any change in an order or a position.
        Call this method whenever a position or an order is updated.
        """
        self.__balance.totalUnrealizedProfit = 0
        self.__balance.totalOpenOrderInitialMargin = 0
        self.__balance.totalMaintMargin = 0
        self.__balance.totalPositionInitialMargin = 0
        self.__balance.totalPositionIsolatedMargin = 0

        for position in self.__open_positions.values():
            self.__balance.totalMaintMargin += position.maintenanceMargin
            self.__balance.totalUnrealizedProfit += position.unrealizedPnl
            match position.marginMode:
                case MarginMode.cross:
                    self.__balance.totalPositionInitialMargin += position.initialMargin
                case MarginMode.isolated:
                    self.__balance.totalPositionIsolatedMargin += position.isolatedMargin

        for order in self.fetch_open_orders():
            if order.orderAction.isClosing:
                continue
            assumed_fee_rate = 0.001
            leverage = self.get_leverage(order.symbol)
            self.__balance.totalOpenOrderInitialMargin += (
                (order.price or (self.get_last_price(order.symbol) * 1.0005 if order.positionSide.isLong else 1.0))
                * order.amount
                * (1 + assumed_fee_rate)
                / leverage
            )

    @profile
    def __validate_price(
        self, order: Order, contingent_sl: ContingentOrder | None = None, contingent_tp: ContingentOrder | None = None
    ) -> None:
        last_price = self.get_last_price(order.symbol)
        entry_price = None

        match order.type:
            case OrderType.market:
                assert order.price is None
                entry_price = last_price
            case OrderType.limit:
                assert order.price is not None
                entry_price = order.price
            case OrderType.stop:
                assert order.price is not None
                assert order.stopPrice is not None
                entry_price = order.price
            case OrderType.stop_market:
                assert order.price is None
                entry_price = order.stopPrice
            case OrderType.take_profit:
                assert order.price is not None
                assert order.stopPrice is not None
                entry_price = order.price
            case OrderType.take_profit_market:
                assert order.price is None
                assert order.stopPrice is not None
                entry_price = order.stopPrice
            case _:
                raise ValueError(f"Invalid order type: {order.type}")

        assert entry_price is not None

        if contingent_sl is not None:
            if order.positionSide.isLong:
                assert contingent_sl.triggerPrice < entry_price
            else:
                assert contingent_sl.triggerPrice > entry_price

        if contingent_tp is not None:
            if order.positionSide.isLong:
                assert contingent_tp.triggerPrice > entry_price
            else:
                assert contingent_tp.triggerPrice < entry_price

        if order.type in (OrderType.stop, OrderType.stop_market):
            assert order.stopPrice is not None and (
                order.stopPrice > last_price if order.side.isBuy else order.stopPrice < last_price
            )

        if order.type in (OrderType.take_profit, OrderType.take_profit_market):
            assert order.stopPrice is not None and (
                order.stopPrice < last_price if order.side.isBuy else order.stopPrice > last_price
            )

    @profile
    def __get_open_position(self, symbol: Symbol, position_side: PositionSide) -> Position | None:
        return self.__open_positions.get((symbol, position_side))
