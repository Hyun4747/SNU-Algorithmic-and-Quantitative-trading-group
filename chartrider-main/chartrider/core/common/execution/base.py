from abc import ABC, abstractmethod

from chartrider.core.common.broker.base import BaseBroker
from chartrider.core.strategy.presets import StrategyPreset


class BaseExecutionHandler(ABC):
    def __init__(
        self,
        broker: BaseBroker,
        strategy_preset: StrategyPreset,
    ) -> None:
        self.broker = broker
        self.strategy_preset = strategy_preset
        self.strategies = strategy_preset.strategies
        for strategy in self.strategies:
            broker.register_strategy(strategy)

    @abstractmethod
    def run(self) -> None:
        ...
