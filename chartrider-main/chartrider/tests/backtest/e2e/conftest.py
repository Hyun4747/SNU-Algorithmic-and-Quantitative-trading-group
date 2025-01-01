from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List
from unittest.mock import MagicMock

import numpy as np
import pytest
from pydantic import BaseModel
from pytest_mock import MockerFixture

from chartrider.core.backtest.broker import BacktestBroker
from chartrider.core.backtest.repository import BacktestRepository
from chartrider.core.common.repository.candle.repository import BaseCandleRepository
from chartrider.core.common.repository.contingent.repository import (
    ContingentInfoBaseRepository,
    ContingentInfoDBRepository,
)
from chartrider.core.common.repository.eventmonitor.monitor import EventMonitor
from chartrider.core.common.repository.models import Balance, Timeframe
from chartrider.core.strategy.base import EventDrivenStrategy
from chartrider.database.connection import DBSessionFactory
from chartrider.utils.data import MultiAssetCandleData
from chartrider.utils.symbols import Symbol
from chartrider.utils.timeutils import Timestamp

FOLDER_PATH = Path(__file__).parent.absolute()
DATA_LENGTH = 1000


@pytest.fixture
def initial_balance() -> Balance:
    return Balance.initial_balance(cash=10000000)


@pytest.fixture
def contingent_repository(db_session_factory: DBSessionFactory) -> ContingentInfoBaseRepository:
    # return ContingentInfoBacktestRepository(user_id="test")
    return ContingentInfoDBRepository(db_session_factory, testnet=False, user_id="test")


@pytest.fixture
def backtest_repository(
    initial_balance: Balance,
    contingent_repository: ContingentInfoBaseRepository,
    backtest_candle_repository: BaseCandleRepository,
    event_monitor: EventMonitor,
):
    repository = BacktestRepository(
        initial_balance,
        candle_repository=backtest_candle_repository,
        contingent_info_repository=contingent_repository,
        event_monitor=EventMonitor(exchange=None),
    )
    return repository


@pytest.fixture
def backtest_broker(backtest_repository: BacktestRepository) -> BacktestBroker:
    broker = BacktestBroker(repository=backtest_repository, event_monitor=EventMonitor(exchange=None))
    broker.equity_history = np.tile(np.nan, DATA_LENGTH + 1)
    broker.register_strategy(DummyStrategy(symbol=Symbol.BTC))
    return broker


class CandleMocker:
    class Candle(BaseModel):
        open: float
        high: float
        low: float
        close: float
        volume: float

        def tuple(self) -> tuple[float, float, float, float, float]:
            return (self.open, self.high, self.low, self.close, self.volume)

    def __init__(self, mocker: MockerFixture, repository: BacktestRepository, broker: BacktestBroker):
        self.mocker = mocker
        self.repository = repository
        self.broker = broker
        self.current_timestamp: int = 1
        self.mocker.patch.object(BacktestBroker, "data_length", return_value=DATA_LENGTH)

    def patch_method(self, method: Callable, return_value: Any):
        if isinstance(method, MagicMock):
            method.return_value = return_value
            return
        self.mocker.patch.object(
            method.__self__,
            method.__name__,
            return_value=return_value,
        )

    def __construct_candle_with_defaults(
        self,
        close: int,
        open: int | None = None,
        high: int | None = None,
        low: int | None = None,
        volume: int | None = None,
    ) -> Candle:
        if open is None:
            open = close
        if high is None:
            high = max(open, close) + 1
        if low is None:
            low = min(open, close) - 1
        if volume is None:
            volume = 1000
        return self.Candle(
            open=float(open),
            high=float(high),
            low=float(low),
            close=float(close),
            volume=float(volume),
        )

    def assume_current_candle(
        self,
        close: int,
        open: int | None = None,
        high: int | None = None,
        low: int | None = None,
        volume: int | None = None,
    ) -> int:
        candle = self.__construct_candle_with_defaults(open=open, high=high, low=low, close=close, volume=volume)
        self.patch_method(self.repository.get_last_price, return_value=candle.close)
        self.patch_method(self.repository.get_next_timestamp, return_value=self.current_timestamp)
        self.patch_method(self.broker.get_last_ohlcv, return_value=(*candle.tuple(), self.current_timestamp))
        self.patch_method(self.repository.get_last_low_high, return_value=(candle.low, candle.high))
        self.current_timestamp += 1
        return self.current_timestamp - 1


@pytest.fixture
def candle_mocker(
    mocker: MockerFixture, backtest_repository: BacktestRepository, backtest_broker: BacktestBroker
) -> CandleMocker:
    return CandleMocker(mocker, backtest_repository, backtest_broker)


class DummyStrategy(EventDrivenStrategy):
    def __init__(self, symbol: Symbol) -> None:
        super().__init__([symbol])

    @property
    def slug(self) -> str:
        return "dummy"

    def setup(self) -> None:
        raise NotImplementedError

    def update_indicators(self) -> None:
        raise NotImplementedError

    def next(self) -> None:
        raise NotImplementedError


class FakeCandleRepository(BaseCandleRepository):
    def download_realtime_candle_data(
        self, symbol: Symbol, timeframe: Timeframe = Timeframe.m1
    ) -> Coroutine[Any, Any, None]:
        raise NotImplementedError

    def fetch_candle_data(
        self,
        symbol: Symbol,
        start: Timestamp,
        end: Timestamp,
        timeframe: Timeframe = Timeframe.m1,
        limit: int | None = None,
        descending: bool = False,
    ) -> MultiAssetCandleData:
        raise NotImplementedError

    def fetch_candle_data_bulk(
        self,
        symbols: List[Symbol],
        start: Timestamp,
        end: Timestamp,
        timeframe: Timeframe = Timeframe.m1,
        limit: int | None = None,
        descending: bool = False,
    ) -> Dict[Symbol, MultiAssetCandleData]:
        raise NotImplementedError

    def fetch_recent_candle_data(
        self, symbol: Symbol, limit: int, timeframe: Timeframe = Timeframe.m1
    ) -> MultiAssetCandleData:
        raise NotImplementedError

    async def close(self) -> None:
        raise NotImplementedError


@pytest.fixture
def backtest_candle_repository() -> BaseCandleRepository:
    return FakeCandleRepository()
