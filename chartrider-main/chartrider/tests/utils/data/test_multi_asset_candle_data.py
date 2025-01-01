import math

import pandas as pd
import pytest

from chartrider.tests.utils.data.conftest import generate_candle_data
from chartrider.utils.data import MultiAssetCandleData
from chartrider.utils.symbols import Symbol


def test_combine_candle_data_basic():
    candles = generate_candle_data(Symbol.BTC, timestamp_offset=0, rows=100)
    eth = generate_candle_data(Symbol.ETH, timestamp_offset=0, rows=100)
    candles.combine(eth)
    assert len(candles.open.symbols) == 2
    assert len(candles.df.columns) == 10
    assert len(candles.df) == 100
    assert candles.open[Symbol.BTC][0] == 0
    assert candles.open[Symbol.ETH][0] == 0
    assert candles.open[Symbol.BTC][9] == 9
    assert candles.open[Symbol.ETH][9] == 9


def test_combine_candle_data_offset():
    candles = generate_candle_data(Symbol.BTC, timestamp_offset=0, rows=100)
    eth = generate_candle_data(Symbol.ETH, timestamp_offset=50, rows=100)
    candles.combine(eth)
    assert len(candles.df) == 150
    assert candles.open[Symbol.BTC][0] == 0
    assert candles.open[Symbol.ETH][50] == 0
    assert math.isnan(candles.open[Symbol.BTC][100])
    assert candles.open[Symbol.ETH][100] == 50
    assert candles.open[Symbol.ETH][149] == 99


def test_combine_candle_override():
    candles = generate_candle_data(Symbol.BTC, timestamp_offset=0, rows=100)
    btc_2 = generate_candle_data(Symbol.BTC, timestamp_offset=50, rows=100)
    candles.combine(btc_2)
    assert len(candles.df) == 150
    assert candles.open[Symbol.BTC][0] == 0
    assert candles.open[Symbol.BTC][50] == 0
    assert candles.open[Symbol.BTC][100] == 50
    assert candles.open[Symbol.BTC][149] == 99


def test_combine_candle_override_with_multi_symbols():
    candles = generate_candle_data(Symbol.BTC, timestamp_offset=0, rows=100)
    eth = generate_candle_data(Symbol.ETH, timestamp_offset=0, rows=100)
    candles.combine(eth)

    btc_2 = generate_candle_data(Symbol.BTC, timestamp_offset=50, rows=100)
    candles.combine(btc_2)
    assert len(candles.df) == 150
    assert candles.open[Symbol.BTC][0] == 0
    assert candles.open[Symbol.ETH][0] == 0
    assert candles.open[Symbol.BTC][49] == 49
    assert candles.open[Symbol.BTC][50] == 0
    assert candles.open[Symbol.ETH][50] == 50
    assert candles.open[Symbol.BTC][100] == 50
    assert candles.open[Symbol.ETH][99] == 99
    assert candles.open[Symbol.BTC][149] == 99


def test_combine_empty_dataframe():
    empty = MultiAssetCandleData(pd.DataFrame())
    candles = generate_candle_data(Symbol.BTC, timestamp_offset=0, rows=100)
    empty.combine(candles)
    assert len(candles.df) == 100
    assert candles.open[Symbol.BTC][0] == 0
    assert candles.open[Symbol.BTC][99] == 99


def test_candle_data_resize():
    candles = generate_candle_data(Symbol.BTC, timestamp_offset=0, rows=100)
    candles.set_length(50)
    assert len(candles) == 50
    assert candles.open[Symbol.BTC][0] == 0
    assert candles.open[Symbol.BTC][49] == 49
    with pytest.raises(IndexError):
        candles.open[Symbol.BTC][50]

    candles.set_length(51)
    assert len(candles) == 51
    assert candles.open[Symbol.BTC][50] == 50


def test_first_valid_index():
    candles = generate_candle_data(Symbol.BTC, timestamp_offset=0, rows=100, leading_nan_rows=10)
    assert candles.first_valid_index() == 10


def test_ohlcv_last():
    candles = generate_candle_data(Symbol.BTC, timestamp_offset=0, rows=100)
    eth = generate_candle_data(Symbol.ETH, timestamp_offset=0, rows=100)
    candles.combine(eth)
    o, h, l, c, v, t = candles.ohlcv_last(Symbol.BTC)  # noqa
    assert o == 99
    assert h == 100
    assert l == 101
    assert c == 102
    assert v == 103
    assert t == 1627776000000 + 99 * 1000


def test_truncate():
    candles = generate_candle_data(Symbol.BTC, timestamp_offset=0, rows=100)
    candles.set_length(80)

    last_timestamp = candles.timestamp_last
    ohlcv_last = candles.ohlcv_last(Symbol.BTC)
    candles.truncate_to(30)
    assert len(candles._data_array) == 30
    assert len(candles) == 10
    assert candles.open[Symbol.BTC][0] == 70
    assert candles.open[Symbol.BTC][9] == 79
    assert candles.timestamp_last == last_timestamp
    assert candles.ohlcv_last(Symbol.BTC) == ohlcv_last


def test_combine_and_truncate():
    candles = generate_candle_data(Symbol.BTC, timestamp_offset=0, rows=100)
    candles_added = generate_candle_data(Symbol.BTC, timestamp_offset=100, rows=2)
    candles.combine(candles_added)
    last_ohlcv = candles.ohlcv_last(Symbol.BTC)
    candles.truncate_to(100)
    assert len(candles) == 100
    assert last_ohlcv == candles.ohlcv_last(Symbol.BTC)


def test_invalid_truncate_value():
    candles = generate_candle_data(Symbol.BTC, timestamp_offset=0, rows=100)
    candles.truncate_to(101)  # do nothing
    assert len(candles) == 100
    candles.truncate_to(100)  # do nothing
    assert len(candles) == 100
    with pytest.raises(ValueError):
        candles.truncate_to(0)
    with pytest.raises(ValueError):
        candles.truncate_to(-1)


def test_truncate_more_than_current_length():
    candles = generate_candle_data(Symbol.BTC, timestamp_offset=0, rows=100)
    candles.set_length(50)
    with pytest.raises(ValueError):
        candles.truncate_to(30)


def test_truncate_less_than_current_length():
    candles = generate_candle_data(Symbol.BTC, timestamp_offset=0, rows=100)
    candles.set_length(50)
    candles.truncate_to(80)
    assert len(candles) == 30
