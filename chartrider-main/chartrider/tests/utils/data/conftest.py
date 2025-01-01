import math

import pandas as pd

from chartrider.utils.data import MultiAssetCandleData
from chartrider.utils.symbols import Symbol


def generate_candle_data(
    symbol: Symbol,
    timestamp_offset: int,
    rows: int,
    leading_nan_rows: int = 0,
) -> MultiAssetCandleData:
    candle_dicts = [
        dict(
            timestamp=1627776000000 + (timestamp_offset + i) * 1000,
            open=i,
            high=i + 1,
            low=i + 2,
            close=i + 3,
            volume=i + 4,
        )
        for i in range(rows)
    ]

    dataframe = pd.DataFrame(candle_dicts)
    dataframe["date"] = pd.to_datetime(dataframe["timestamp"], unit="ms", utc=True)
    dataframe.drop("timestamp", axis=1, inplace=True)
    dataframe.interpolate(method="ffill", inplace=True)  # type: ignore
    dataframe.set_index("date", inplace=True)
    dataframe.iloc[:leading_nan_rows, :3] = math.nan
    columns = pd.MultiIndex.from_product([["open", "high", "low", "close", "volume"], [symbol]])
    dataframe.columns = columns
    return MultiAssetCandleData(dataframe)
