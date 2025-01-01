from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from functools import partial
from typing import TYPE_CHECKING, Callable

from loguru import logger

from chartrider.core.common.repository.eventmonitor.monitor import EventMonitor
from chartrider.core.common.repository.models import (
    Balance,
    ClientOrderId,
    ContingentOrder,
    Order,
    OrderAction,
    OrderStatus,
    Position,
    PositionSide,
    TimeInForce,
)
from chartrider.core.strategy.signpost import Signposter
from chartrider.utils.data import Indicator, MultiAssetCandleData, SymbolColumnData
from chartrider.utils.symbols import Symbol

if TYPE_CHECKING:
    from chartrider.core.common.broker.base import BaseBroker


class BaseStrategy(ABC):
    def __init__(
        self,
        symbols: list[Symbol],
        candles_needed: int = 0,
    ) -> None:
        self.symbols = symbols
        self.estimated_candles_needed = candles_needed
        self.strategy_orders: dict[Symbol, set[Order]] = defaultdict(set)
        self.signposter = Signposter()

        # broker could be injected later
        self.broker: BaseBroker = None  # type: ignore

    @property
    @abstractmethod
    def slug(self) -> str:
        """A unique identifier for the strategy."""
        ...

    @abstractmethod
    def setup(self) -> None:
        """Set up all necessary variables.
        This method is called exactly once before the strategy is run."""
        ...

    @abstractmethod
    def update_indicators(self) -> None:
        """Set up all necessary indicators.
        This method is called multiple times during the live trading session."""
        ...

    def set_broker(self, broker: BaseBroker) -> None:
        self.broker = broker
        broker.event_monitor.did_force_liquidate.subscribe(self.did_force_liquidate)

    @property
    def event_monitor(self) -> EventMonitor:
        return self.broker.event_monitor

    @property
    def indicators(self) -> list[Indicator]:
        return [indicator for indicator in self.__dict__.values() if isinstance(indicator, Indicator)]

    def indicator_set_length(self, length: int) -> None:
        for indicator in self.indicators:
            indicator.set_length(length)

    @abstractmethod
    def next(self) -> None:
        ...

    @property
    def indicator_candles_needed(self) -> int:
        return 1 + max((indicator.first_valid_index() for indicator in self.indicators), default=0)

    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self.symbols})"

    @property
    def candle_data(self) -> MultiAssetCandleData:
        return self.broker.candle_data

    def get_last_price(self, symbol: Symbol) -> float:
        return self.broker.repository.get_last_price(symbol)

    @property
    def current_timestamp(self) -> int:
        return self.candle_data.timestamp_last

    @property
    def balance(self) -> Balance:
        return self.broker.repository.fetch_balance()

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
    ) -> Order | None:
        """
        Create an order.

        Note that client_order_id are set automatically.
        """
        client_order_id = ClientOrderId(strategy=self.slug, timestamp=self.current_timestamp)
        order = self.broker.repository.create_order(
            symbol=symbol,
            action=action,
            amount=amount,
            price=price,
            stop_price=stop_price,
            contingent_sl=contingent_sl,
            contingent_tp=contingent_tp,
            time_in_force=time_in_force,
            client_order_id=client_order_id,
        )

        if order is None:
            logger.warning(f"Failed to create order for strategy {self.slug}")
            return

        if order.status not in (OrderStatus.open, OrderStatus.closed):
            logger.warning(f"Order {order} is created but has an unexpected status {order.status}")

        order.signposter = self.signposter
        return order

    def place_order(
        self,
        symbol: Symbol,
        action: OrderAction,
        amount: float,
        price: float | None,
        contingent_sl: ContingentOrder | None = None,
        contingent_tp: ContingentOrder | None = None,
        stop_price: float | None = None,
        time_in_force: TimeInForce = TimeInForce.GTC,
    ) -> Order | None:
        """
        Place an opening order (open_long / open_short)
        and save the created order object into `self.unfilled_orders`
        """
        if action.isClosing:
            logger.warning(f"Order action {action} is not supported for place_strategy_order().")
            return

        order = self.create_order(
            symbol=symbol,
            action=action,
            amount=amount,
            price=price,
            contingent_sl=contingent_sl,
            contingent_tp=contingent_tp,
            stop_price=stop_price,
            time_in_force=time_in_force,
        )
        if order is None:
            return

        self.strategy_orders[symbol].add(order)

        self.signposter.begin_interval(
            signpost_id=order.id,
            symbol=symbol,
            name=f"Place order {order.id}",
            timestamp=order.timestamp or self.current_timestamp,
            action=action,
            amount=amount,
            order_cost=order.cost,
        )

        return order

    def get_strategy_orders(self, symbol: Symbol) -> set[Order]:
        return self.strategy_orders[symbol].copy()

    def sync_order_status(self, order: Order) -> OrderStatus:
        if order.status == OrderStatus.closed:
            return order.status

        if order.status != OrderStatus.open:
            self.strategy_orders[order.symbol].discard(order)
            return order.status

        # Now the before-sync status must be open
        synced_order = self.broker.repository.fetch_order(order)
        if synced_order is None:
            raise RuntimeError(f"Order {order} cannot be found in the repository.")

        order.status = synced_order.status
        return order.status

    def cancel_order(self, order: Order) -> None:
        """
        Cancel an open order of this strategy.
        Note that the contingent orders are automatically canceled by the repository.
        """
        if order.status != OrderStatus.open:
            return

        self.broker.repository.cancel_order(order)
        self.strategy_orders[order.symbol].discard(order)

        self.signposter.emit_event(
            name=f"Cancelled order {order.id}",
            description="Cancelled order.",
            timestamp=order.timestamp or self.current_timestamp,
        )

    def cancel_all_orders(self, symbol: Symbol | None = None) -> None:
        """Cancel all unfilled orders of this strategy."""
        if symbol is None:
            for symbol in self.symbols:
                self.cancel_all_orders(symbol)
            return

        for order in list(self.strategy_orders[symbol]):
            self.cancel_order(order)

    @abstractmethod
    def clear_all(self) -> None:
        """Clear all filled/unfilled orders and positions of this strategy."""
        ...

    ##### To test strategy consistency in backtest #####
    ### (전략 구현 후 백테스트 했을 때 문제 없을 시 삭제 예정) ###
    def post_order_execution(self, order: Order) -> Order | None:
        return None
        synced_order = self.__sync_unfilled_order(order)

        if synced_order is not None and synced_order.status != OrderStatus.closed:
            logger.warning(f"Order {order} is not closed yet, probably due to partial fill.")
            return

        return synced_order

    def did_force_liquidate(self, symbol: Symbol, side: PositionSide) -> None:
        for order in list(self.strategy_orders[symbol]):
            if order.positionSide != side:
                continue

            order_status = self.sync_order_status(order)

            if order_status == OrderStatus.closed:
                self.strategy_orders[symbol].discard(order)
                continue

            if order_status == OrderStatus.open:
                self.cancel_order(order)
                continue

    def make_indicator(
        self,
        data: SymbolColumnData,
        plot: bool = True,
        figure_id: int | None = None,
    ) -> Indicator:
        """Constructs an Indicator from the given data.

        Args:
            data (SymbolColumnData): The data to be used for the indicator.
            plot (bool, optional): Determines whether the indicator should be plotted. Defaults to True.
            figure_id (int | None, optional): The ID of the figure to plot the indicator on.
                                              If None, it will be drawn on OHLC chart. Defaults to None.
        """
        return Indicator(
            data,
            plot=plot,
            figure_id=figure_id,
        )

    def __setattr__(self, name: str, value: object) -> None:
        super().__setattr__(name, value)

        if isinstance(value, Indicator):
            value.name = name


class EventDrivenStrategy(BaseStrategy):
    """
    EventDriveStrategy

    Note: Contingent orders are only supported for EventDrivenStrategy.
    """

    def liquidate_order(self, order: Order) -> None:
        """
        Liquidate a closed order of this strategy by creating an order in the opposite direction.
        The associated contingent orders are then canceled.

        Note that partial liquidation or liquidation by limit order is not supported yet.
        """
        order_status = self.sync_order_status(order)

        if order_status != OrderStatus.closed:
            logger.warning(f"Order {order} cannot be liquidated, as it is not closed yet.")
            return

        # Check if the order is already liquidated by contingent orders.
        if self.broker.repository.is_liquidated_by_contingent(order):
            self.strategy_orders[order.symbol].discard(order)
            return

        if synced_order := self.broker.repository.fetch_order(order):
            # Fetch the order again to get the latest trades.
            order = synced_order

        for trade in order.trades:
            liq_order = self.create_order(
                symbol=order.symbol,
                action=OrderAction.close_long if order.positionSide.isLong else OrderAction.close_short,
                amount=trade.amount,
                price=None,  # TODO: support limit order
            )

            if liq_order is None:
                logger.warning(f"Failed to create liquidate order for strategy {self.slug}")
                return

            if liq_order.status not in (OrderStatus.open, OrderStatus.closed):
                logger.warning(f"Order {liq_order} is created but has an unexpected status {liq_order.status}")
                return

            self.signposter.end_interval(
                signpost_id=order.id,
                symbol=order.symbol,
                name=f"Liquidate order {order.id}",
                timestamp=liq_order.timestamp or self.current_timestamp,
                trade_amount=trade.amount,
                trade_price=trade.price,
            )

        self.broker.repository.cancel_contingent_orders(original_order=order)
        self.strategy_orders[order.symbol].discard(order)

    def liquidate_all_orders(self, symbol: Symbol | None = None) -> None:
        """Liquidate all active orders of this strategy."""

        if symbol is None:
            for symbol in self.symbols:
                self.liquidate_all_orders(symbol)
            return

        for order in list(self.strategy_orders[symbol]):
            self.liquidate_order(order)

    def clear_all(self) -> None:
        self.cancel_all_orders()
        self.liquidate_all_orders()


class RebalancingStrategy(BaseStrategy):
    """
    RebalancingStrategy

    Note1: Contingent orders are not supported for RebalancingStrategy.
    Note2: Only one RebalancingStrategy can be registered to a broker.
    """

    def set_broker(self, broker: BaseBroker) -> None:
        super().set_broker(broker)

        # For rebalancing, we may need to open orders before the margin is released,
        # and thus, for now, we double the leverage to avoid margin error.
        for symbol in self.symbols:
            curr_leverge = self.broker.repository.get_leverage(symbol)
            self.broker.repository.set_leverage(symbol, 2 * curr_leverge)

    def fetch_positions(self) -> dict[Symbol, Position]:
        position_list = self.broker.repository.fetch_positions(self.symbols)

        # Assert that a symbol does not have multiple positions for a rebalancing strategy.
        assert len(position_list) == len(set([position.symbol for position in position_list]))

        current_positions = {position.symbol: position for position in position_list}
        return current_positions

    def liquidate_position(self, symbol: Symbol, position: Position | None = None) -> None:
        """
        Liquidate the current position of the symbol.
        """
        if symbol not in self.symbols:
            logger.warning(f"Symbol {symbol} is not in the symbols of strategy {self.slug}")

        if position is None:
            position = self.fetch_positions()[symbol]

        action = OrderAction.close_long if position.side.isLong else OrderAction.close_short
        liq_order = self.create_order(symbol, action, position.contracts, None)  # TODO: support limit order

        if liq_order is None:
            logger.warning(f"Failed to create liquidate order for strategy {self.slug}")
            return

        if liq_order.status not in (OrderStatus.open, OrderStatus.closed):
            logger.warning(f"Order {liq_order} is created but has an unexpected status {liq_order.status}")
            return

    def liquidate_all_positions(self) -> None:
        """
        Liquidate all current positions.
        """
        current_positions = self.fetch_positions()
        for symbol, position in current_positions.items():
            self.liquidate_position(symbol, position)

    def clear_all(self) -> None:
        self.cancel_all_orders()
        self.liquidate_all_positions()

    def rebalance(
        self, target_portfolio: dict[Symbol, float], target_prices: dict[Symbol, float] | None = None
    ) -> None:
        """
        Rebalance the current portfoilo to the target amount.
        """
        self.cancel_all_orders()

        current_positions = self.fetch_positions()

        tasks = []
        for symbol in self.symbols:
            curr_position = current_positions.get(symbol)
            target_amount = abs(target_portfolio[symbol])
            target_side = PositionSide.long if target_portfolio[symbol] > 0 else PositionSide.short
            target_price = target_prices[symbol] if target_prices is not None else None

            tasks.extend(self.rebalance_single(symbol, curr_position, target_side, target_amount, target_price))

        # FIXME: multi-threading
        for task in tasks:
            task()

    def rebalance_single(
        self,
        symbol: Symbol,
        curr_position: Position | None,
        target_side: PositionSide,
        target_amount: float,
        target_price: float | None = None,
    ) -> list[Callable]:
        if target_amount == 0:
            if curr_position is not None:
                return [partial(self.liquidate_position, symbol=symbol, position=curr_position)]
            return []

        if curr_position is None:
            place_action = OrderAction.open_long if target_side.isLong else OrderAction.open_short
            return [partial(self.place_order, symbol, place_action, target_amount, target_price)]

        if curr_position.side != target_side:
            place_action = OrderAction.open_long if target_side.isLong else OrderAction.open_short
            return [
                partial(self.liquidate_position, symbol, curr_position),
                partial(self.place_order, symbol, place_action, target_amount, target_price),
            ]

        curr_amount = curr_position.contracts

        if target_side.isLong:
            if curr_amount > target_amount:
                return [
                    partial(
                        self.create_order, symbol, OrderAction.close_long, curr_amount - target_amount, target_price
                    )
                ]
            else:
                return [
                    partial(self.place_order, symbol, OrderAction.open_long, target_amount - curr_amount, target_price)
                ]
        else:
            if curr_amount > target_amount:
                return [
                    partial(
                        self.create_order, symbol, OrderAction.close_short, curr_amount - target_amount, target_price
                    )
                ]
            else:
                return [
                    partial(
                        self.place_order, symbol, OrderAction.open_short, target_amount - curr_amount, target_price
                    )
                ]
