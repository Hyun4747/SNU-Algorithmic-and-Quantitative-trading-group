from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from functools import cached_property
from typing import TYPE_CHECKING

import numpy as np

from chartrider.core.common.repository.eventmonitor.monitor import EventMonitor
from chartrider.core.common.repository.models import MarginMode
from chartrider.core.strategy.base import BaseStrategy
from chartrider.utils.data import MultiAssetCandleData
from chartrider.utils.symbols import Symbol

if TYPE_CHECKING:
    from chartrider.core.common.repository.base import BaseRepository


class BaseBroker(ABC):
    def __init__(self, repository: BaseRepository, event_monitor: EventMonitor) -> None:
        self.repository = repository
        self.event_monitor = event_monitor

        self._registered_strategies: dict[str, BaseStrategy] = {}
        self.equity_history: np.ndarray = np.array([])

    def register_strategy(self, strategy: BaseStrategy) -> None:
        strategy.set_broker(self)
        assert strategy.slug not in self._registered_strategies, f"Strategy {strategy.slug} already registered"
        self._registered_strategies[strategy.slug] = strategy

    def set_isolated_margin_mode(self) -> None:
        for symbol in self.symbols:
            self.repository.set_margin_mode(symbol, MarginMode.isolated)

    @property
    def registered_strategies_count(self) -> int:
        return len(self._registered_strategies)

    @abstractmethod
    def prepare_initial_data(self, start: datetime, end: datetime) -> None:
        ...

    @cached_property
    def max_candles_needed(self) -> int:
        return max(strategy.estimated_candles_needed for strategy in self._registered_strategies.values())

    @cached_property
    def max_candles_needed_for_indicators(self) -> int:
        return max(strategy.indicator_candles_needed for strategy in self._registered_strategies.values())

    @property
    def data_length(self) -> int:
        return len(self.repository.candle_data)

    @property
    def candle_data(self) -> MultiAssetCandleData:
        return self.repository.candle_data

    @property
    def symbols(self) -> set[Symbol]:
        return set(symbol for strategy in self._registered_strategies.values() for symbol in strategy.symbols)
