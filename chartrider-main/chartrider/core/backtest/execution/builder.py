from datetime import datetime
from typing import Iterator

from chartrider.core.backtest.broker import BacktestBroker
from chartrider.core.backtest.execution.handler import BacktestExecutionHandler
from chartrider.core.backtest.execution.prompt import (
    BacktestPeriod,
    prompt_backtest_periods,
    prompt_backtest_strategies,
)
from chartrider.core.backtest.repository import BacktestRepository
from chartrider.core.common.repository.candle.repository import (
    CandleAPIRepository,
    CandleDBRepository,
    CandleRepository,
)
from chartrider.core.common.repository.contingent.repository import (
    ContingentInfoInMemoryRepository,
)
from chartrider.core.common.repository.eventmonitor.monitor import EventMonitor
from chartrider.core.common.repository.models import Balance
from chartrider.core.strategy.presets import StrategyPreset
from chartrider.database.connection import DBSessionFactory
from chartrider.utils.exchange import ExchangeFactory


def build_handler_from_preset(
    start: datetime, end: datetime, strategy_preset: StrategyPreset
) -> BacktestExecutionHandler:
    session_factory = DBSessionFactory()
    candle_db_repository = CandleDBRepository(session_factory=session_factory)
    candle_api_repository = CandleAPIRepository(
        exchange=ExchangeFactory.get_public_exchange(use_testnet=False),
        async_exchange=ExchangeFactory.get_public_async_exchange(use_testnet=False),
    )
    candle_repository = CandleRepository(db_repository=candle_db_repository, api_repository=candle_api_repository)
    event_monitor = EventMonitor(exchange=None)
    repository = BacktestRepository(
        initial_balance=Balance.initial_balance(),
        candle_repository=candle_repository,
        event_monitor=event_monitor,
        contingent_info_repository=ContingentInfoInMemoryRepository(user_id="backtest"),
    )
    broker = BacktestBroker(repository=repository, event_monitor=event_monitor)
    return BacktestExecutionHandler(
        start=start,
        end=end,
        broker=broker,
        strategy_preset=strategy_preset,
    )


def build_handlers_from_prompt(strategy_presets: list[StrategyPreset]) -> Iterator[BacktestExecutionHandler]:
    periods: list[BacktestPeriod] = prompt_backtest_periods()
    presets: list[StrategyPreset] = prompt_backtest_strategies(strategy_presets)
    for period in periods:
        for strategy_preset in presets:
            yield build_handler_from_preset(period.start, period.end, strategy_preset)
