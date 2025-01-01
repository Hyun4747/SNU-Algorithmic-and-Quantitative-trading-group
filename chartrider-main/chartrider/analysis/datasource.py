from __future__ import annotations

from uuid import UUID

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict

from chartrider.analysis.stat import StatResult
from chartrider.core.common.repository.models import Order, Trade
from chartrider.core.strategy.signpost import Signpost, SignpostID
from chartrider.utils.data import Indicator
from chartrider.utils.symbols import Symbol
from chartrider.utils.timeutils import TimeUtils

SignpostData = dict[SignpostID, list[Signpost]]


class SymbolDataSource(BaseModel):
    id: UUID
    symbol: Symbol

    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray
    timestamp: np.ndarray

    long_amount_history: np.ndarray
    short_amount_history: np.ndarray
    long_notional_history: np.ndarray
    short_notional_history: np.ndarray

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def get_close_price(self, target_timestamp):
        idx = np.searchsorted(self.timestamp, target_timestamp)
        return self.close[idx]

    def slice(self, start: float, end: float) -> SymbolDataSource:
        start_idx = np.searchsorted(self.timestamp, start)
        end_idx = np.searchsorted(self.timestamp, end)
        return SymbolDataSource(
            id=self.id,
            symbol=self.symbol,
            open=self.open[start_idx:end_idx],
            high=self.high[start_idx:end_idx],
            low=self.low[start_idx:end_idx],
            close=self.close[start_idx:end_idx],
            volume=self.volume[start_idx:end_idx],
            timestamp=self.timestamp[start_idx:end_idx],
            long_amount_history=self.long_amount_history[start_idx:end_idx],
            short_amount_history=self.short_amount_history[start_idx:end_idx],
            long_notional_history=self.long_notional_history[start_idx:end_idx],
            short_notional_history=self.short_notional_history[start_idx:end_idx],
        )


class StrategyDataSource(BaseModel):
    id: UUID
    strategy_name: str
    strategy_slug: str
    indicators: list[Indicator]
    orders: list[Order]
    trades: list[Trade]
    long_trades: list[Trade]
    short_trades: list[Trade]
    symbol_sources: list[SymbolDataSource]
    signposts: SignpostData
    model_config = ConfigDict(arbitrary_types_allowed=True)

    def signposts_by_symbol(self, symbol: Symbol) -> SignpostData:
        return {k: v for k, v in self.signposts.items() if v[0].symbol == symbol}


class PlotDataSource(BaseModel):
    id: UUID
    name: str
    description: str
    equity_history: np.ndarray
    strategy_sources: list[StrategyDataSource]
    resample_freq_min: int = 1
    stat: StatResult

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def timestamp_array(self) -> np.ndarray:
        return self.strategy_sources[0].symbol_sources[0].timestamp


def as_datetime_array(timestamp_array: np.ndarray) -> pd.DatetimeIndex:
    return pd.to_datetime(timestamp_array, unit="ms", utc=True)


def as_datestring_array(timestamp_array: np.ndarray) -> list[str]:
    return [TimeUtils.timestamp_to_datestring(timestamp) for timestamp in timestamp_array]
