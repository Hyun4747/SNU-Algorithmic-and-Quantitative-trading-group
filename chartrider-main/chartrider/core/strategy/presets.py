from pydantic import BaseModel, ConfigDict

from chartrider.core.strategy.base import BaseStrategy


class StrategyPreset(BaseModel):
    name: str
    description: str = ""
    strategies: list[BaseStrategy]

    model_config: ConfigDict = ConfigDict(arbitrary_types_allowed=True)

    def __str__(self) -> str:
        return f"{self.name}"

    def full_description(self) -> str:
        return f"{self.name} - {self.description}"
