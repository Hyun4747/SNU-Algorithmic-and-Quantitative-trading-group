from chartrider.core.common.repository import CandleDBRepository
from chartrider.core.common.repository.models import Timeframe
from chartrider.utils.symbols import Symbol


def test_get_dataset(candle_db_repository: CandleDBRepository):
    symbol = Symbol.BTC
    timeframe = Timeframe.m1
    dataset = candle_db_repository.get_or_create_dataset(symbol, timeframe)
    assert dataset is not None
    assert dataset.symbol == "btc"
    assert dataset.timeframe == "1m"


def test_candles_bulk_insert(candle_db_repository: CandleDBRepository):
    symbol = Symbol.BTC
    timeframe = Timeframe.m1
    ohlcvs = [
        (0, 1, 2, 3, 4, 5),
        (1, 1, 2, 3, 4, 5),
        (2, 1, 2, 3, 4, 5),
    ]
    candle_db_repository.update_or_create_candles(symbol, timeframe, ohlcvs)
    candles = candle_db_repository.get_candles_dataframe(symbol, start=0, end=2, timeframe=timeframe)
    assert len(candles) == 3


def test_get_candles_start_end(candle_db_repository: CandleDBRepository):
    symbol = Symbol.BTC
    timeframe = Timeframe.m1
    ohlcvs = [
        (0, 1, 2, 3, 4, 5),
        (1, 1, 2, 3, 4, 5),
        (2, 1, 2, 3, 4, 5),
    ]
    candle_db_repository.update_or_create_candles(symbol, timeframe, ohlcvs)
    candles = candle_db_repository.get_candles_dataframe(symbol, start=1, end=2, timeframe=timeframe)
    assert len(candles) == 2
    assert candles.iloc[0].timestamp == 1
    assert candles.iloc[1].timestamp == 2


def test_get_candles_limit(candle_db_repository: CandleDBRepository):
    symbol = Symbol.BTC
    timeframe = Timeframe.m1
    ohlcvs = [
        (0, 1, 2, 3, 4, 5),
        (1, 1, 2, 3, 4, 5),
        (2, 1, 2, 3, 4, 5),
    ]
    candle_db_repository.update_or_create_candles(symbol, timeframe, ohlcvs)
    candles = candle_db_repository.get_candles_dataframe(symbol, start=0, end=3, limit=2, timeframe=timeframe)
    assert len(candles) == 2
    assert candles.iloc[0].timestamp == 0
    assert candles.iloc[1].timestamp == 1


def test_get_candles_descending(candle_db_repository: CandleDBRepository):
    symbol = Symbol.BTC
    timeframe = Timeframe.m1
    ohlcvs = [
        (0, 1, 2, 3, 4, 5),
        (1, 1, 2, 3, 4, 5),
        (2, 1, 2, 3, 4, 5),
    ]
    candle_db_repository.update_or_create_candles(symbol, timeframe, ohlcvs)
    candles = candle_db_repository.get_candles_dataframe(symbol, start=0, end=2, descending=True, timeframe=timeframe)
    assert len(candles) == 3
    assert candles.iloc[0].timestamp == 2
    assert candles.iloc[1].timestamp == 1
    assert candles.iloc[2].timestamp == 0


def test_get_candles_descending_limit(candle_db_repository: CandleDBRepository):
    symbol = Symbol.BTC
    timeframe = Timeframe.m1
    ohlcvs = [
        (0, 1, 2, 3, 4, 5),
        (1, 1, 2, 3, 4, 5),
        (2, 1, 2, 3, 4, 5),
    ]
    candle_db_repository.update_or_create_candles(symbol, timeframe, ohlcvs)
    candles = candle_db_repository.get_candles_dataframe(
        symbol, start=0, end=2, descending=True, limit=2, timeframe=timeframe
    )
    assert len(candles) == 2
    assert candles.iloc[0].timestamp == 2
    assert candles.iloc[1].timestamp == 1


def test_get_recent_candles(candle_db_repository: CandleDBRepository):
    symbol = Symbol.BTC
    timeframe = Timeframe.m1
    ohlcvs = [
        (0, 1, 2, 3, 4, 5),
        (1, 1, 2, 3, 4, 5),
        (2, 1, 2, 3, 4, 5),
    ]
    candle_db_repository.update_or_create_candles(symbol, timeframe, ohlcvs)
    candles = candle_db_repository.get_recent_candles(symbol, timeframe, limit=1)
    assert len(candles) == 1
    assert candles.iloc[0].timestamp == 2


def test_candles_bulk_insert_on_conflict(candle_db_repository: CandleDBRepository):
    symbol = Symbol.BTC
    timeframe = Timeframe.m1
    ohlcvs = [
        (0, 1, 2, 3, 4, 5),
        (1, 1, 2, 3, 4, 5),
        (2, 1, 2, 3, 4, 5),
    ]
    candle_db_repository.update_or_create_candles(symbol, timeframe, ohlcvs)

    new_ohlcvs = [
        (0, 1, 2, 3, 4, 5),
        (1, 1, 2, 3, 4, 5),
        (2, 9, 9, 9, 9, 9),
    ]
    candle_db_repository.update_or_create_candles(symbol, timeframe, new_ohlcvs)

    candles = candle_db_repository.get_candles_dataframe(symbol, start=0, end=2, timeframe=timeframe)
    assert candles.iloc[-1].timestamp == 2
    assert candles.iloc[-1].open == 9
    assert candles.iloc[-1].high == 9
    assert candles.iloc[-1].low == 9
    assert candles.iloc[-1].close == 9
    assert candles.iloc[-1].volume == 9
