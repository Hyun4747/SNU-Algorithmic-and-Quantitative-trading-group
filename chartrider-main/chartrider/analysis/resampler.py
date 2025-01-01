from __future__ import annotations

from enum import Enum
from functools import cache
from typing import Any

import numpy as np
import pandas as pd
from bokeh.models import Range1d

from chartrider.analysis.datasource import (
    PlotDataSource,
    StrategyDataSource,
    SymbolDataSource,
    as_datestring_array,
    as_datetime_array,
)
from chartrider.utils.data import Indicator, SymbolColumnData


class DataSourceResampler:
    MAX_CANDLES = 1000

    @classmethod
    def resample(cls, datasource: PlotDataSource, freq: ResampleFrequency) -> PlotDataSource:
        if len(datasource.timestamp_array) < cls.MAX_CANDLES:
            return datasource
        if datasource.resample_freq_min == freq.minutes:
            return datasource

        return cls.__resampling_datasource(datasource, freq)

    @classmethod
    def __resampling_datasource(
        cls,
        datasource: PlotDataSource,
        resample_freq: ResampleFrequency,
    ) -> PlotDataSource:
        return PlotDataSource(
            id=datasource.id,
            name=datasource.name,
            description=datasource.description,
            equity_history=cls.__resampling_equity_history(datasource, resample_freq),
            strategy_sources=[
                cls.__resampling_strategy(strategy_source, resample_freq)
                for strategy_source in datasource.strategy_sources
            ],
            resample_freq_min=resample_freq.minutes,
            stat=datasource.stat,
        )

    @classmethod
    def __resampling_strategy(
        cls,
        strategy_source: StrategyDataSource,
        resample_freq: ResampleFrequency,
    ) -> StrategyDataSource:
        return StrategyDataSource(
            id=strategy_source.id,
            strategy_name=strategy_source.strategy_name,
            strategy_slug=strategy_source.strategy_slug,
            indicators=[
                cls.__resampling_indicator(indicator, resample_freq) for indicator in strategy_source.indicators
            ],
            orders=strategy_source.orders,
            trades=strategy_source.trades,
            long_trades=strategy_source.long_trades,
            short_trades=strategy_source.short_trades,
            symbol_sources=[
                cls.__resampling_symbol_data(source, resample_freq) for source in strategy_source.symbol_sources
            ],
            signposts=strategy_source.signposts,
        )

    @classmethod
    def __resampling_indicator(
        cls,
        indicator: Indicator,
        resample_freq: ResampleFrequency,
    ) -> Indicator:
        df = indicator.original_indicator.df()
        resampled_df = df.resample(resample_freq.pandas_name, label="right").mean()
        data = SymbolColumnData.from_dataframe(resampled_df)
        return Indicator(
            indicator=data,
            plot=indicator.plot,
            figure_id=indicator.figure_id,
            name=indicator.name,
        )

    @classmethod
    def __resampling_equity_history(cls, datasource: PlotDataSource, resample_freq: ResampleFrequency):
        equity_series = pd.Series(
            datasource.equity_history,
            index=pd.to_datetime(datasource.timestamp_array, unit="ms", utc=True),
        )

        equity_series = equity_series.resample(resample_freq.pandas_name, label="right").agg("last")
        return equity_series.to_numpy()

    @classmethod
    def __resampling_symbol_data(
        cls,
        source: SymbolDataSource,
        resample_freq: ResampleFrequency,
    ) -> SymbolDataSource:
        df = pd.DataFrame(
            {
                "open": source.open,
                "high": source.high,
                "low": source.low,
                "close": source.close,
                "volume": source.volume,
                "long_amount_history": source.long_amount_history,
                "short_amount_history": source.short_amount_history,
                "long_notional_history": source.long_notional_history,
                "short_notional_history": source.short_notional_history,
            },
            index=pd.to_datetime(source.timestamp, unit="ms", utc=True),
        )

        aggregation_rule: Any = dict(
            open="first",
            high="max",
            low="min",
            close="last",
            volume="sum",
            long_amount_history="last",
            short_amount_history="last",
            long_notional_history="last",
            short_notional_history="last",
        )
        resampled_df = df.resample(resample_freq.pandas_name, label="right").agg(aggregation_rule)
        return SymbolDataSource(
            id=source.id,
            symbol=source.symbol,
            open=resampled_df.open.to_numpy(),
            high=resampled_df.high.to_numpy(),
            low=resampled_df.low.to_numpy(),
            close=resampled_df.close.to_numpy(),
            volume=resampled_df.volume.to_numpy(),
            timestamp=resampled_df.index.values.astype(np.int64) // 10**6,
            long_amount_history=resampled_df.long_amount_history.to_numpy(),
            short_amount_history=resampled_df.short_amount_history.to_numpy(),
            long_notional_history=resampled_df.long_notional_history.to_numpy(),
            short_notional_history=resampled_df.short_notional_history.to_numpy(),
        )

    @classmethod
    def get_resample_freq(cls, x0: float, x1: float) -> ResampleFrequency:
        timespan_ms = x1 - x0
        timespan_minutes = timespan_ms // (1000 * 60)
        minutes_per_candle = timespan_minutes / cls.MAX_CANDLES
        return ResampleFrequency.minimum_frequency(minutes_per_candle)


class ResampledDataProvider:
    def __init__(self, data_source: PlotDataSource, x_range: Range1d):
        self.__data_source = data_source
        self.__cache: dict[ResampleFrequency, PlotDataSource] = {}
        self.__x_range = x_range

    def __resample(self, start: float, end: float) -> PlotDataSource:
        freq = DataSourceResampler.get_resample_freq(start, end)
        if freq == ResampleFrequency.t1:
            return self.__data_source
        if freq in self.__cache:
            return self.__cache[freq]
        datasource = DataSourceResampler.resample(self.__data_source, freq)
        self.__cache[ResampleFrequency.from_minutes(datasource.resample_freq_min)] = datasource
        return datasource

    def resample_frequency(self) -> ResampleFrequency:
        datasource = self.__resample(self.visible_start, self.visible_end)
        return ResampleFrequency.from_minutes(datasource.resample_freq_min)

    def candlestick_width(self) -> float:
        return self.resample_frequency().minutes * 60 * 1000

    def symbol_datasource(self, symbol_datasource: SymbolDataSource) -> SymbolDataSource:
        datasource = self.__resample(self.visible_start, self.visible_end)
        for strategy_source in datasource.strategy_sources:
            for source in strategy_source.symbol_sources:
                if source.id == symbol_datasource.id:
                    return source.slice(self.visible_start, self.visible_end)
        raise ValueError(f"SymbolDataSource {symbol_datasource.id} not found in resampled data source")

    def indicators(self, strategy_datasource: StrategyDataSource) -> list[Indicator]:
        datasource = self.__resample(self.visible_start, self.visible_end)
        for source in datasource.strategy_sources:
            if source.id == strategy_datasource.id:
                return [indicator.sliced(self.visible_start, self.visible_end) for indicator in source.indicators]
        raise ValueError(f"StrategyDataSource {strategy_datasource.id} not found in resampled data source")

    def datetime_array(self) -> pd.DatetimeIndex:
        datasource = self.__resample(self.visible_start, self.visible_end)
        timestamps = self.sliced(datasource.timestamp_array, datasource.timestamp_array)
        return as_datetime_array(timestamps)

    def datestring_array(self) -> list[str]:
        datasource = self.__resample(self.visible_start, self.visible_end)
        timestamps = self.sliced(datasource.timestamp_array, datasource.timestamp_array)
        return as_datestring_array(timestamps)

    def equity_history(self) -> np.ndarray:
        datasource = self.__resample(self.visible_start, self.visible_end)
        return self.sliced(datasource.timestamp_array, datasource.equity_history)

    def running_max(self) -> np.ndarray:
        datasource = self.__resample(self.visible_start, self.visible_end)
        running_max = np.fmax.accumulate(datasource.equity_history)
        return self.sliced(datasource.timestamp_array, running_max)

    @property
    def visible_start(self) -> float:
        if isinstance(self.__x_range.start, pd.Timestamp):
            return self.__x_range.start.timestamp() * 1000  # type: ignore
        return self.__x_range.start  # type: ignore

    @property
    def visible_end(self) -> float:
        if isinstance(self.__x_range.end, pd.Timestamp):
            return self.__x_range.end.timestamp() * 1000  # type: ignore
        return self.__x_range.end  # type: ignore

    def sliced(self, timestamp_array: np.ndarray, data: np.ndarray) -> np.ndarray:
        assert len(timestamp_array) == len(data)
        start_idx = np.searchsorted(timestamp_array, self.visible_start)
        end_idx = np.searchsorted(timestamp_array, self.visible_end)
        return data[start_idx:end_idx]


class ResampleFrequency(Enum):
    t1 = "1T"
    t5 = "5T"
    t10 = "10T"
    t15 = "15T"
    t30 = "30T"
    h1 = "1H"
    h2 = "2H"
    h3 = "3H"
    h4 = "4H"
    h6 = "6H"
    h8 = "8H"
    h12 = "12H"
    d1 = "1D"
    w1 = "1W"
    m1 = "1M"
    m2 = "2M"
    m3 = "3M"
    m6 = "6M"

    @property
    def minutes(self) -> int:
        name = self.pandas_name
        return (
            int(name[0:-1])
            * {
                "t": 1,
                "h": 60,
                "d": 60 * 24,
                "w": 60 * 24 * 7,
                "m": 60 * 24 * 30,
            }[name[-1].lower()]
        )

    @cache
    @staticmethod
    def from_minutes(minutes: int) -> ResampleFrequency:
        for frequency in ResampleFrequency:
            if frequency.minutes == minutes:
                return frequency
        raise ValueError(f"No frequency found for {minutes} minutes")

    @staticmethod
    def minimum_frequency(minutes: float) -> ResampleFrequency:
        for frequency in ResampleFrequency:
            if frequency.minutes >= minutes:
                return frequency
        return ResampleFrequency.m1

    @property
    def pandas_name(self) -> str:
        return str(self.value)
