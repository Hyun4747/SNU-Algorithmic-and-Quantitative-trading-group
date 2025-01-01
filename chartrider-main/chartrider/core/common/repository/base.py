from abc import ABC, abstractmethod
from typing import Iterable

import pandas as pd

from chartrider.core.common.repository.models import (
    Balance,
    ClientOrderId,
    ContingentOrder,
    MarginMode,
    Order,
    OrderAction,
    OrderSide,
    OrderType,
    Position,
    TimeInForce,
    Trade,
)
from chartrider.utils.data import MultiAssetCandleData
from chartrider.utils.symbols import Symbol
from chartrider.utils.timeutils import Timestamp


class BaseRepository(ABC):
    def __init__(self) -> None:
        self.candle_data: MultiAssetCandleData = MultiAssetCandleData(pd.DataFrame())

    @abstractmethod
    def next(self) -> None:
        ...

    @abstractmethod
    def fetch_balance(self) -> Balance:
        ...

    @abstractmethod
    def fetch_order(self, order: Order) -> Order | None:
        ...

    @abstractmethod
    def fetch_orders(self, symbol: Symbol) -> list[Order]:
        ...

    @abstractmethod
    def fetch_open_orders(self, symbol: Symbol) -> list[Order]:
        ...

    @abstractmethod
    def fetch_closed_orders(self, symbol: Symbol) -> list[Order]:
        ...

    @abstractmethod
    def fetch_trades(self, symbol: Symbol | None = None) -> list[Trade]:
        ...

    @abstractmethod
    def fetch_ohlcv(self, symbol: Symbol, timeframe: str, since: Timestamp, until: Timestamp | None) -> None:
        ...

    @abstractmethod
    def create_order(
        self,
        symbol: Symbol,
        action: OrderAction,
        amount: float,
        price: float | None,
        stop_price: float | None = None,
        contingent_sl: ContingentOrder | None = None,
        contingent_tp: ContingentOrder | None = None,
        time_in_force: TimeInForce = TimeInForce.GTC,
        client_order_id: ClientOrderId | None = None,
    ) -> Order | None:
        ...

    @abstractmethod
    def is_liquidated_by_contingent(self, order: Order) -> bool:
        ...

    @abstractmethod
    def cancel_order(self, order: Order) -> Order | None:
        ...

    @abstractmethod
    def fetch_positions(self, symbols: Iterable[str]) -> list[Position]:
        ...

    @abstractmethod
    def get_last_price(self, symbol: Symbol) -> float:
        ...

    @abstractmethod
    def cancel_contingent_orders(self, original_order: Order) -> None:
        ...

    @abstractmethod
    def cancel_all_orders(self, symbol: Symbol) -> None:
        ...

    @abstractmethod
    def set_leverage(self, symbol: Symbol, leverage: int) -> None:
        ...

    @abstractmethod
    def get_leverage(self, symbol: Symbol) -> int:
        ...

    @abstractmethod
    def set_margin_mode(self, symbol: Symbol, margin_mode: MarginMode):
        ...

    async def close(self):
        ...

    @staticmethod
    def get_order_type(
        action: OrderAction,
        price: float | None,
        stop_price: float | None = None,
        last_price: float | None = None,
    ) -> OrderType:
        """Determine the order type based on the provided parameters."""

        if action.orderSide == OrderSide.sell:
            is_take_profit = stop_price is not None and last_price is not None and last_price < stop_price
        elif action.orderSide == OrderSide.buy:
            is_take_profit = stop_price is not None and last_price is not None and last_price > stop_price
        else:
            raise ValueError("Invalid action")

        if price is None and stop_price is None:
            return OrderType.market
        elif price is not None and stop_price is None:
            return OrderType.limit
        elif price is None and stop_price is not None:
            return OrderType.stop_market if not is_take_profit else OrderType.take_profit_market
        elif price is not None and stop_price is not None:
            return OrderType.stop if not is_take_profit else OrderType.take_profit
        else:
            raise ValueError("Invalid order type")
