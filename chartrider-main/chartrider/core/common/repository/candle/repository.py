import asyncio
import io
import threading
from abc import ABC, abstractmethod
from typing import Dict, List, cast

import ccxt
import ccxt.pro
import numpy as np
import pandas
import pandas as pd
from loguru import logger
from sqlalchemy import Selectable, delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from tqdm import tqdm, trange

from chartrider.core.common.repository.candle.schemas import Candle, Dataset
from chartrider.core.common.repository.candle.utils import find_holes
from chartrider.core.common.repository.models import Timeframe
from chartrider.database.connection import DBSessionFactory
from chartrider.utils.data import MultiAssetCandleData
from chartrider.utils.eventloop import AsyncEventLoop
from chartrider.utils.symbols import Symbol
from chartrider.utils.timeutils import Timestamp, TimeUtils

TOHLCVs = list[tuple[int, float, float, float, float, float]]
MAX_WORKERS = 5
DEBUG_MODE = False


async def gather_coroutines(coroutines):
    return await asyncio.gather(*coroutines, return_exceptions=False)


def read_sql_tuned(stmt: Selectable, session: Session, symbol):
    start = time.time() if DEBUG_MODE else 0
    engine = session.bind
    compiled = stmt.compile(engine)
    query = compiled.string % compiled.params
    copy_sql = "COPY ({query}) TO STDOUT WITH CSV HEADER".format(query=query)
    conn = session.connection().connection
    cur = conn.cursor()
    store = io.StringIO()
    cur.copy_expert(copy_sql, store)
    store.seek(0)

    if DEBUG_MODE:
        print(
            f"""
        [{threading.current_thread().name}]
        [{symbol}] Query Executed On Connection: {conn.dbapi_connection}
        [{symbol}] Query Execution time: {time.time() - start}
        """
        )

    session.commit()
    return pandas.read_csv(store)


class BaseCandleRepository(ABC):
    @abstractmethod
    async def download_realtime_candle_data(
        self,
        symbol: Symbol,
        timeframe: Timeframe = Timeframe.m1,
    ) -> None:
        ...

    @abstractmethod
    def fetch_candle_data(
        self,
        symbol: Symbol,
        start: Timestamp,
        end: Timestamp,
        timeframe: Timeframe = Timeframe.m1,
        limit: int | None = None,
        descending: bool = False,
    ) -> MultiAssetCandleData:
        ...

    @abstractmethod
    def fetch_candle_data_bulk(
        self,
        symbols: List[Symbol],
        start: Timestamp,
        end: Timestamp,
        timeframe: Timeframe = Timeframe.m1,
        limit: int | None = None,
        descending: bool = False,
    ) -> Dict[Symbol, MultiAssetCandleData]:
        ...

    @abstractmethod
    def fetch_recent_candle_data(
        self,
        symbol: Symbol,
        limit: int,
        timeframe: Timeframe = Timeframe.m1,
    ) -> MultiAssetCandleData:
        ...

    @abstractmethod
    async def close(self):
        ...


class CandleRepository(BaseCandleRepository):
    def __init__(
        self,
        api_repository: "CandleAPIRepository",
        db_repository: "CandleDBRepository",
    ) -> None:
        self.api_repository = api_repository
        self.db_repository = db_repository
        self.watching_symbols: set[tuple[Symbol, Timeframe]] = set()
        self.internal_loop = AsyncEventLoop()
        self.internal_loop.start_loop(num_threads=MAX_WORKERS)

    def __back_fill_missing_candle_data(
        self,
        symbol: Symbol,
        start: Timestamp,
        end: Timestamp,
        saved_timestamp_list: list[Timestamp],
        timeframe: Timeframe = Timeframe.m1,
    ) -> None:
        saved_timestamps = np.array(saved_timestamp_list or [])

        if start not in saved_timestamps:
            saved_timestamps = np.insert(saved_timestamps, 0, start)
        if end not in saved_timestamps:
            saved_timestamps = np.append(saved_timestamps, end)

        holes = find_holes(saved_timestamps, normalize_factor=timeframe.milliseconds)

        if len(holes) == 0:
            return

        with tqdm(holes) as pbar:
            for hole_start, hole_end in pbar:
                # update progress bar
                dates = [TimeUtils.timestamp_to_datetime(date).strftime("%Y.%m.%d") for date in [hole_start, hole_end]]
                pbar.set_description(f"[{symbol.value.upper()}] {' - '.join(dates)}")
                self.__download_candle_data(symbol, hole_start, hole_end, timeframe)

    def __download_candle_data(
        self,
        symbol: Symbol,
        start: Timestamp,
        end: Timestamp,
        timeframe: Timeframe = Timeframe.m1,
    ) -> None:
        entries_per_call = 1000
        one_call_ms = timeframe.milliseconds * entries_per_call
        remainder_ms = (end - start) % one_call_ms
        num_calls = (end - start) // one_call_ms + int(remainder_ms >= 0)
        with trange(num_calls) as pbar:
            for i in pbar:
                since = start + i * one_call_ms
                ohlcvs = self.api_repository.fetch_ohlcv(symbol, since, timeframe, entries_per_call)
                self.db_repository.update_or_create_candles(symbol, timeframe, ohlcvs)
                if len(ohlcvs) != entries_per_call and i != num_calls - 1:
                    logger.warning(f"Expected {entries_per_call} entries, but received {len(ohlcvs)} entries.")

                pbar.set_description(
                    f"[{symbol.value.upper()}] {TimeUtils.timestamp_to_datestring(ohlcvs[-1][0], compact=True)}"
                )

    async def download_realtime_candle_data(
        self,
        symbol: Symbol,
        timeframe: Timeframe = Timeframe.m1,
    ) -> None:
        if (symbol, timeframe) in self.watching_symbols:
            return
        self.watching_symbols.add((symbol, timeframe))
        while True:
            try:
                ohlcvs = await self.api_repository.watch_ohlcv(symbol, timeframe)
                self.db_repository.update_or_create_candles(symbol, timeframe, ohlcvs)
            except Exception as e:
                logger.error(e)
                await asyncio.sleep(10)

    def fetch_candle_data(
        self,
        symbol: Symbol,
        start: Timestamp,
        end: Timestamp,
        timeframe: Timeframe = Timeframe.m1,
        limit: int | None = None,
        descending: bool = False,
    ) -> MultiAssetCandleData:
        candles_df = self.db_repository.get_candles_dataframe(symbol, start, end, timeframe, limit, descending)
        expected_length = limit if limit else ((end - start) // timeframe.milliseconds + 1)

        # load data from api to db
        if len(candles_df) != expected_length:
            self.__back_fill_missing_candle_data(symbol, start, end, candles_df["timestamp"].tolist(), timeframe)
            candles_df = self.db_repository.get_candles_dataframe(symbol, start, end, timeframe, limit, descending)

        candles_data = self.__to_multiasset_data(symbol, candles_df)
        return candles_data

    def fetch_candle_data_bulk(
        self,
        symbols: List[Symbol],
        start: Timestamp,
        end: Timestamp,
        timeframe: Timeframe = Timeframe.m1,
        limit: int | None = None,
        descending: bool = False,
    ) -> Dict[Symbol, MultiAssetCandleData]:
        coro = gather_coroutines(
            [
                self.internal_loop.perform(self.fetch_candle_data, symbol, start, end, timeframe, limit, descending)
                for symbol in symbols
            ]
        )

        results = self.internal_loop.await_task(coro)
        return dict(zip(symbols, results))

    def fetch_recent_candle_data(
        self,
        symbol: Symbol,
        limit: int,
        timeframe: Timeframe = Timeframe.m1,
    ) -> MultiAssetCandleData:
        candles = self.db_repository.get_recent_candles(symbol, timeframe, limit)
        return self.__to_multiasset_data(symbol, candles)

    def __to_multiasset_data(self, symbol: Symbol, candles_df: pd.DataFrame) -> MultiAssetCandleData:
        dataframe = candles_df
        dataframe["date"] = pd.to_datetime(dataframe["timestamp"], unit="ms", utc=True)
        dataframe.drop("timestamp", axis=1, inplace=True)
        dataframe.interpolate(method="ffill", inplace=True)  # type: ignore
        dataframe.set_index("date", inplace=True)
        columns = pd.MultiIndex.from_product([["open", "high", "low", "close", "volume"], [symbol]])
        dataframe.columns = columns
        return MultiAssetCandleData(dataframe)

    async def close(self):
        await self.api_repository.close()
        self.db_repository.close()
        self.internal_loop.stop_loop()


class CandleAPIRepository:
    def __init__(self, exchange: ccxt.binanceusdm, async_exchange: ccxt.pro.binanceusdm) -> None:
        self.exchange = exchange
        self.async_exchange = async_exchange

    def fetch_ohlcv(
        self,
        symbol: Symbol,
        since: Timestamp,
        timeframe: Timeframe = Timeframe.m1,
        limit: int = 1000,
    ) -> TOHLCVs:
        ohlcvs = self.exchange.fetch_ohlcv(symbol, timeframe.__str__(), since, limit)
        if headers := self.exchange.last_response_headers:
            used_weight_per_minute = int(headers["X-MBX-USED-WEIGHT-1M"])
        else:
            raise ValueError("No headers found in response")

        # binance api rate limit : 1200 weights per minute
        # call above (fetch_ohlcv) takes 5 weights, which is 4 calls per second
        if used_weight_per_minute >= 1200:
            logger.info(f"Rate Limited: {used_weight_per_minute}")
            logger.info("Resuming after a minute")
            time.sleep(60)

        ohlcvs = cast(TOHLCVs, ohlcvs)
        return ohlcvs

    async def watch_ohlcv(self, symbol: Symbol, timeframe: Timeframe = Timeframe.m1) -> TOHLCVs:
        ohlcvs = await self.async_exchange.watch_ohlcv(symbol, timeframe.__str__())
        ohlcvs = cast(TOHLCVs, ohlcvs)
        return ohlcvs

    async def close(self):
        await self.async_exchange.close()


class CandleDBRepository:
    def __init__(self, session_factory: DBSessionFactory) -> None:
        self.session_factory = session_factory

    @property
    def session(self) -> Session:
        return self.session_factory.scoped_session()

    def get_or_create_dataset(self, symbol: Symbol, timeframe: Timeframe) -> Dataset:
        dataset = self.session.query(Dataset).filter_by(symbol=symbol, timeframe=timeframe.__str__()).first()
        if dataset is None:
            dataset = Dataset(symbol=symbol, timeframe=timeframe.__str__())
            self.session.add(dataset)
            self.session.commit()
        return dataset

    def get_candle_timestamps(
        self,
        symbol: Symbol,
        timeframe: Timeframe,
        start: Timestamp,
        end: Timestamp,
    ) -> list[Timestamp]:
        dataset = self.get_or_create_dataset(symbol, timeframe)

        stmt = (
            select(Candle.timestamp)
            .where(Candle.dataset_id == dataset.id)
            .where(Candle.timestamp >= start)
            .where(Candle.timestamp <= end)
            .order_by(Candle.timestamp)
        )

        result = self.session.execute(stmt).scalars().all()
        return list(result)

    def get_recent_candles(
        self,
        symbol: Symbol,
        timeframe: Timeframe,
        limit: int,
    ) -> pd.DataFrame:
        dataset = self.get_or_create_dataset(symbol, timeframe)
        stmt = (
            select(
                Candle.timestamp,
                Candle.open,
                Candle.high,
                Candle.low,
                Candle.close,
                Candle.volume,
            )
            .where(Candle.dataset_id == dataset.id)
            .order_by(Candle.timestamp.desc())
            .limit(limit)
        )

        return read_sql_tuned(stmt, self.session, symbol)  # type: ignore

    def get_candles_dataframe(
        self,
        symbol: Symbol,
        start: Timestamp,
        end: Timestamp,
        timeframe: Timeframe = Timeframe.m1,
        limit: int | None = None,
        descending: bool = False,
    ) -> pd.DataFrame:
        dataset = self.get_or_create_dataset(symbol, timeframe)

        stmt = (
            select(Candle.timestamp, Candle.open, Candle.high, Candle.low, Candle.close, Candle.volume)
            .where(Candle.dataset_id == dataset.id)
            .where(Candle.timestamp >= start)
            .where(Candle.timestamp <= end)
        )

        if descending:
            stmt = stmt.order_by(Candle.timestamp.desc())
        else:
            stmt = stmt.order_by(Candle.timestamp.asc())

        if limit is not None:
            stmt = stmt.limit(limit)

        return read_sql_tuned(stmt, self.session, symbol)

    def update_or_create_candles(
        self,
        symbol: Symbol,
        timeframe: Timeframe,
        ohlcvs: TOHLCVs,
    ):
        dataset = self.get_or_create_dataset(symbol, timeframe)

        stmt = insert(Candle).values(
            [
                {
                    "dataset_id": dataset.id,
                    "timestamp": timestamp,
                    "open": open,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": volume,
                }
                for timestamp, open, high, low, close, volume in ohlcvs
            ],
        )

        stmt = stmt.on_conflict_do_update(
            index_elements=[Candle.dataset_id, Candle.timestamp],
            set_=dict(
                stmt.excluded.items(),
            ),
        )

        self.session.execute(stmt)
        self.session.commit()

    def delete_candles(
        self,
        symbol: Symbol,
        timeframe: Timeframe,
    ):
        dataset = self.get_or_create_dataset(symbol, timeframe)
        stmt = delete(Candle).where(Candle.dataset_id == dataset.id)
        self.session.execute(stmt)
        self.session.commit()

    def close(self):
        try:
            self.session.commit()
            self.session.close()
        except Exception as e:
            logger.error(f"Failed to close session: {e}")


if __name__ == "__main__":
    import time
    from datetime import datetime

    from chartrider.utils.exchange import ExchangeFactory

    candle_api_repository = CandleAPIRepository(
        exchange=ExchangeFactory.get_public_exchange(use_testnet=False),
        async_exchange=ExchangeFactory.get_public_async_exchange(use_testnet=False),
    )
    candle_db_repository = CandleDBRepository(session_factory=DBSessionFactory())

    candle_repository = CandleRepository(
        api_repository=candle_api_repository,
        db_repository=candle_db_repository,
    )

    DEBUG_MODE = False
    RUN_ASYNC = True
    symbols = Symbol.all()[:3]
    print(f"Symbols to test: {symbols}\nAsync mode: {RUN_ASYNC}")

    start_time = time.time()
    if not RUN_ASYNC:
        result1 = {
            symbol: candle_repository.fetch_candle_data(
                symbol,
                start=TimeUtils.timestamp_in_ms(datetime(2023, 1, 1)),
                end=TimeUtils.timestamp_in_ms(datetime(2024, 1, 1)),
                timeframe=Timeframe.m1,
            )
            for symbol in symbols
        }
        print(f"[Synchronous] Execution time for {symbols}: {time.time() - start_time}s")
    else:
        result2 = candle_repository.fetch_candle_data_bulk(
            symbols,
            start=TimeUtils.timestamp_in_ms(datetime(2023, 1, 1)),
            end=TimeUtils.timestamp_in_ms(datetime(2024, 1, 1)),
            timeframe=Timeframe.m1,
        )
        print(f"[Asynchronous] Execution time for {len(symbols)} symbols: {time.time() - start_time}s")
