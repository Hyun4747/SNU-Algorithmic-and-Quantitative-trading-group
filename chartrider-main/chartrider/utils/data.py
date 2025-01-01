from __future__ import annotations

from collections import defaultdict
from typing import Any, cast

import numpy as np
import pandas as pd

from chartrider.utils.symbols import Symbol


class BoundedArray:
    def __init__(self, array: np.ndarray, length: int):
        self.__array = array
        self.__current_length = length

    def __getitem__(self, key) -> Any:
        if isinstance(key, int):
            if key < 0:
                key += self.__current_length
            if key >= self.__current_length or key < 0:
                raise IndexError
            return self.__array[key]
        elif isinstance(key, slice):
            # Adjust slice to handle current_length
            start, stop, step = key.indices(self.__current_length)
            if stop > self.__current_length:
                stop = self.__current_length
            return self.__array[start:stop:step]
        else:
            raise TypeError

    def as_array(self) -> np.ndarray:
        return self.__array[: self.__current_length]


class SymbolColumnData:
    def __init__(
        self,
        data_array: np.ndarray,
        column_map: dict[Symbol, int],
        index: pd.DatetimeIndex,
        length: int | None = None,
    ):
        self.__data_array = data_array
        self.__column_map = column_map
        self.__index = index
        self.__current_length = length or len(data_array)

    def __getitem__(self, symbol: Symbol) -> BoundedArray:
        col_index = self.__column_map[symbol]
        selected_column = self.__data_array[:, col_index]
        return BoundedArray(selected_column, self.__current_length)

    def get_column_indices(self, symbols: list[Symbol] | None) -> list[int]:
        return (
            list(self.__column_map.values()) if symbols is None else [self.__column_map[symbol] for symbol in symbols]
        )

    def get_last(self, symbols: list[Symbol] | None = None) -> np.ndarray:
        return self.__data_array[self.__current_length - 1, self.get_column_indices(symbols)]

    def set_length(self, length: int) -> None:
        self.__current_length = length

    def df(self, symbols: list[Symbol] | None = None) -> pd.DataFrame:
        sliced = self.__data_array[: self.__current_length, self.get_column_indices(symbols)]
        return pd.DataFrame(sliced, columns=symbols or self.symbols, index=self.__index[: self.__current_length])

    def resized(self, length: int) -> SymbolColumnData:
        data = SymbolColumnData(self.__data_array, self.__column_map, index=self.__index)
        data.set_length(length)
        return data

    @property
    def length(self) -> int:
        return self.__current_length

    @property
    def symbols(self) -> list[Symbol]:
        return list(self.__column_map.keys())

    def first_valid_index(self) -> int:
        return _first_valid_index(self.__data_array)

    @staticmethod
    def from_dataframe(df: pd.DataFrame) -> SymbolColumnData:
        return SymbolColumnData(
            data_array=df.values,
            column_map={cast(Symbol, symbol): i for i, symbol in enumerate(df.columns)},
            index=cast(pd.DatetimeIndex, df.index),
        )


class MultiAssetData:
    def __init__(self, df: pd.DataFrame):
        self.__initialize(df)

    def __create_column_map(self, columns: pd.MultiIndex) -> dict[str, dict[Symbol, int]]:
        column_map = defaultdict(dict)
        for idx, (col_name, symbol) in enumerate(columns):
            column_map[col_name][symbol] = idx
        return column_map

    def __convert_to_timestamp(self, index: pd.DatetimeIndex) -> np.ndarray:
        return index.values.astype(np.int64) // 10**6

    def set_length(self, length: int):
        if length > len(self._original_df):
            raise ValueError("Length cannot exceed the number of rows in the original dataframe.")
        self._current_length = length

    def combine(self, new_data: MultiAssetData):
        """
        Combine the new dataframe with the original dataframe,
        and reset the sliced data to the new dataframe.
        """
        if new_data.df.empty:
            raise ValueError("Cannot combine with empty data")
        if self._original_df.empty:
            self._original_df = new_data.df
        else:
            self._original_df = new_data.df.combine_first(self._original_df)
        self.__initialize(self._original_df)

    def truncate_to(self, desired_length: int):
        if desired_length <= 0:
            raise ValueError("Cannot truncate to a length less than or equal to 0.")
        desired_length = min(desired_length, len(self._original_df))
        if desired_length == len(self._original_df):
            return
        candles_to_truncate = len(self._original_df) - desired_length
        if self._current_length < candles_to_truncate:
            raise ValueError(f"Cannot truncate more than {self._current_length=}.")
        previous_length = self._current_length
        self.__initialize(self._original_df.tail(desired_length))
        self._current_length = previous_length - candles_to_truncate

    def __initialize(self, df: pd.DataFrame) -> None:
        self._original_df = df
        self._data_array = df.values
        self._current_length = len(df)
        self._index = cast(pd.DatetimeIndex, df.index)
        if not df.empty:
            assert isinstance(df.index, pd.DatetimeIndex)
            assert isinstance(df.columns, pd.MultiIndex)
            self.timestamp_array = self.__convert_to_timestamp(df.index)
            self.column_map = self.__create_column_map(df.columns)
        else:
            self.timestamp_array = np.array([], dtype=np.int64)
            self.column_map = dict()

    @property
    def df(self) -> pd.DataFrame:
        return self._original_df.iloc[: self._current_length]

    @property
    def index(self) -> pd.DatetimeIndex:
        return self._index[: self._current_length]

    @property
    def timestamp_last(self) -> int:
        return self.timestamp_array[self._current_length - 1]

    @property
    def timestamp_next(self) -> int:
        return self.timestamp_array[self._current_length]

    def first_valid_index(self) -> int:
        return _first_valid_index(self._data_array)

    def __len__(self) -> int:
        return self._current_length


class MultiAssetCandleData(MultiAssetData):
    @property
    def open(self):
        return SymbolColumnData(self._data_array, self.column_map["open"], self._index, self._current_length)

    @property
    def close(self):
        return SymbolColumnData(self._data_array, self.column_map["close"], self._index, self._current_length)

    @property
    def high(self):
        return SymbolColumnData(self._data_array, self.column_map["high"], self._index, self._current_length)

    @property
    def low(self):
        return SymbolColumnData(self._data_array, self.column_map["low"], self._index, self._current_length)

    @property
    def volume(self):
        return SymbolColumnData(self._data_array, self.column_map["volume"], self._index, self._current_length)

    def ohlcv_last(self, symbol: Symbol) -> tuple[float, float, float, float, float, int]:
        indices = tuple(self.column_map[component][symbol] for component in ["open", "high", "low", "close", "volume"])
        ohlcv_tuple = tuple(self._data_array[self._current_length - 1, indices]) + (self.timestamp_last,)
        return ohlcv_tuple  # type: ignore


class Indicator:
    def __init__(
        self,
        indicator: SymbolColumnData,
        plot: bool = True,
        figure_id: int | None = None,
        name: str | None = None,
    ):
        self.name: str | None = name
        self.original_indicator = indicator
        self.resized_indicator = indicator
        self.plot = plot
        self.figure_id = figure_id

    def __getitem__(self, symbol: Symbol) -> BoundedArray:
        return self.resized_indicator[symbol]

    def get_last(self, symbols: list[Symbol] | None = None) -> np.ndarray:
        return self.resized_indicator.get_last(symbols)

    def set_length(self, length: int) -> None:
        self.resized_indicator = self.original_indicator.resized(length)

    def first_valid_index(self) -> int:
        return self.original_indicator.first_valid_index()

    def sliced(self, start: float, end: float) -> Indicator:
        df = self.original_indicator.df()
        start_date = pd.to_datetime(start, unit="ms", utc=True)
        end_date = pd.to_datetime(end, unit="ms", utc=True)
        sliced_df = df.loc[start_date:end_date]
        indicator = SymbolColumnData.from_dataframe(sliced_df)
        return Indicator(indicator, self.plot, self.figure_id, self.name)

    def __len__(self) -> int:
        return self.resized_indicator.length


def _first_valid_index(data_array: np.ndarray) -> int:
    mask = np.isnan(data_array)
    first_valid_index = np.argmax(~mask, axis=0)
    return np.max(first_valid_index)
