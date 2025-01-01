from datetime import datetime
from typing import Iterator

from dateutil.relativedelta import relativedelta
from pydantic import BaseModel

from chartrider.core.common.utils.prompt import prompt_checkbox
from chartrider.core.strategy.presets import StrategyPreset


class BacktestPeriod(BaseModel):
    start: datetime
    end: datetime

    def __str__(self) -> str:
        return f"{self.start.strftime('%Y.%m.%d')} - {self.end.strftime('%Y.%m.%d')}"


def prompt_backtest_strategies(choices: list[StrategyPreset]) -> list[StrategyPreset]:
    return prompt_checkbox(choices, "Choose the strategies to backtest (no selection defaults to all)")


def prompt_backtest_periods() -> list[BacktestPeriod]:
    choices = list(__generate_period_options())
    return prompt_checkbox(choices, "Choose the periods to backtest (no selection defaults to all)")


def __generate_period_options(
    start_year: int = 2020,
    start_month: int = 7,
    duration: relativedelta = relativedelta(years=1),
    interval: relativedelta = relativedelta(months=6),
) -> Iterator[BacktestPeriod]:
    start_date = datetime(start_year, start_month, 1).astimezone()
    while start_date + duration <= datetime.now().astimezone():
        yield BacktestPeriod(start=start_date, end=start_date + duration)
        start_date += interval

    yield BacktestPeriod(start=datetime(2021, 1, 1).astimezone(), end=datetime(2024, 1, 1).astimezone())
