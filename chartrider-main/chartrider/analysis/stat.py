from datetime import datetime, timedelta
from typing import cast

import numpy as np
import pandas as pd
from pandas import Timedelta
from pydantic import BaseModel

from chartrider.core.common.repository.models import Position, Trade
from chartrider.core.strategy.base import BaseStrategy
from chartrider.utils.data import MultiAssetCandleData
from chartrider.utils.prettyprint import PrettyPrint, PrettyPrintMode
from chartrider.utils.symbols import Symbol
from chartrider.utils.timeutils import TimeUtils


class StatResult(BaseModel):
    created_at: datetime = datetime.now().astimezone()
    start: datetime | None = None
    end: datetime | None = None
    duration: timedelta | None = None
    equity_final: float | None = None
    equity_peak: float | None = None
    rate_of_return: float | None = None
    annual_return: float | None = None
    annual_volatility: float | None = None
    max_drawdown: float | None = None
    avg_drawdown: float | None = None
    max_drawdown_duration: timedelta | None = None
    avg_drawdown_duration: timedelta | None = None
    sharpe_ratio: float | None = None
    sortino_ratio: float | None = None
    risk_return_ratio: float | None = None
    upside_capture_ratio: float | None = None
    downside_capture_ratio: float | None = None
    num_trades: int | None = None
    alpha: float | None = None
    beta: float | None = None

    # per-symbol stats
    positions: dict[str, list[Position]] = dict()
    trades: dict[str, list[Trade]] = dict()
    buy_and_hold_return: dict[str, float] = dict()
    open_total: dict[str, float] = dict()
    realized_pnl: dict[str, float] = dict()
    fees: dict[str, float] = dict()
    ror_fee_included: dict[str, float] = dict()
    win_rate: dict[str, float] = dict()
    profit_factor: dict[str, float] = dict()
    exposure_time: dict[str, float] = dict()

    def format(self, mode: PrettyPrintMode = PrettyPrintMode.terminal) -> str:
        pp = PrettyPrint(mode=mode)

        # Overall stats
        pp.header("Overall stats")
        pp.key_value("Start", self.start)
        pp.key_value("End", self.end)
        pp.key_value("Duration", self.duration)
        pp.key_value("Equity Final [$]", self.equity_final, decimal_places=8)
        pp.key_value("Equity Peak [$]", self.equity_peak, decimal_places=8)
        pp.key_value("Return [%]", (self.rate_of_return or 0) * 100, decimal_places=5, colorize=True)
        pp.key_value("Ann. Return [%]", (self.annual_return or 0) * 100, decimal_places=5, colorize=True)
        pp.key_value("Ann. Volatility [%]", (self.annual_volatility or 0) * 100, decimal_places=5)
        pp.key_value("Max. Drawdown [%]", (self.max_drawdown or 0) * 100, decimal_places=5, colorize=True)
        pp.key_value("Avg. Drawdown [%]", (self.avg_drawdown or 0) * 100, decimal_places=5, colorize=True)
        pp.key_value("Max. Drawdown Duration", self.max_drawdown_duration or timedelta(0))
        pp.key_value("Avg. Drawdown Duration", self.avg_drawdown_duration or timedelta(0))
        pp.key_value("Sharpe Ratio", self.sharpe_ratio, decimal_places=5, colorize=True)
        pp.key_value("Sortino Ratio", self.sortino_ratio, decimal_places=5, colorize=True)
        pp.key_value("Risk Return Ratio", self.risk_return_ratio, decimal_places=5, colorize=True)
        pp.key_value("Upside Capture Ratio", self.upside_capture_ratio, decimal_places=5, colorize=True)
        pp.key_value("Downside Capture Ratio", self.downside_capture_ratio, decimal_places=5, colorize=True)
        pp.key_value("Alpha", self.alpha, decimal_places=5, colorize=True)
        pp.key_value("Beta", self.beta, decimal_places=5)
        pp.key_value("Num. Trades", self.num_trades)

        if self.num_trades == 0:
            pp.newline()
            return pp.result

        # Per-symbol stats
        pp.header("Per-symbol stats", divider="-")
        for symbol in sorted(self.trades.keys()):
            pp.subheader(symbol.upper())
            pp.key_value("Open Total [$]", self.open_total[symbol], decimal_places=8)
            pp.key_value("Realized PnL [$]", self.realized_pnl[symbol], decimal_places=8, colorize=True)
            pp.key_value("Fees [$]", self.fees[symbol], decimal_places=8, colorize=True)
            pp.key_value(
                "Return (including fees) [%]",
                self.ror_fee_included[symbol] * 100,
                decimal_places=5,
                colorize=True,
            )
            pp.key_value(
                "Buy & Hold Return [%]", self.buy_and_hold_return[symbol] * 100, decimal_places=5, colorize=True
            )
            pp.key_value("Win Rate [%]", self.win_rate[symbol] * 100, decimal_places=5)
            pp.key_value("Profit Factor", self.profit_factor[symbol], decimal_places=5)
            pp.key_value("Exposure Time [hrs]", f"{self.exposure_time[symbol]:.2f}")
            pp.key_value("Num. Trades", len(self.trades[symbol]))
            pp.key_value("Num. Positions", len(self.positions[symbol]))
            pp.newline()

        pp.newline()
        return pp.result


class StatAnalyzer:
    def __init__(
        self,
        n_candles_to_skip: int,
        strategies: list[BaseStrategy],
        candle_data: MultiAssetCandleData,
        trades: list[Trade],
        positions: list[Position],
        equity_history: np.ndarray,
        risk_free_rate: float = 0.04,  # 4% annual risk-free rate
        benchmark_symbol: Symbol | None = None,
    ) -> None:
        assert -1 < risk_free_rate < 1
        assert all(
            symbol in candle_data.close.symbols for strategy in strategies for symbol in strategy.symbols
        ), "Not all strategies have OHLCV data"
        assert len(candle_data) == len(equity_history), "OHLCV data and the PnL history has different lengths"
        self.n_candles_to_skip = n_candles_to_skip
        self.strategies = strategies
        self.candle_data = candle_data
        self.dt_index = candle_data._original_df.index[n_candles_to_skip:].tz_convert("Asia/Seoul")  # type: ignore
        self.ts_index = candle_data.timestamp_array[n_candles_to_skip:]

        self.trades = trades
        self.positions = positions
        self.equity_history = equity_history[n_candles_to_skip:]
        self.risk_free_rate = risk_free_rate
        self.benchmark_symbol = benchmark_symbol

        self.result = StatResult()

    def compute(self) -> StatResult:
        # Common stats
        self.result.start = TimeUtils.timestamp_to_datetime(int(self.ts_index[0]))
        self.result.end = TimeUtils.timestamp_to_datetime(int(self.ts_index[-1]))
        self.result.duration = self.result.end - self.result.start
        self.result.equity_final = round(self.equity_history[-1], 8)
        self.result.equity_peak = round(self.equity_history.max(), 8)
        self.result.num_trades = len(self.trades)

        # Drawdown
        dd = 1 - self.equity_history / np.maximum.accumulate(self.equity_history)
        dd_dur = StatAnalyzer.compute_drawdown_duration(pd.Series(dd, index=self.dt_index))
        self.result.max_drawdown = float(-dd.max())
        self.result.avg_drawdown = float(-dd.mean())
        self.result.max_drawdown_duration = cast(Timedelta, dd_dur.max())
        self.result.avg_drawdown_duration = cast(Timedelta, dd_dur.mean())

        # Annualized returns
        day_returns = pd.Series(self.equity_history, index=self.dt_index).resample("D").last().dropna().pct_change()
        gmean_day_return = self.__geometric_mean(day_returns)
        annual_trading_days = 365
        self.result.annual_return = (1 + gmean_day_return) ** annual_trading_days - 1

        # Annualized volatility
        day_volatility = day_returns.var(ddof=int(bool(day_returns.shape)))  # type: ignore
        self.result.annual_volatility = np.sqrt(
            (day_volatility + (1 + gmean_day_return) ** 2) ** annual_trading_days  # type: ignore
            - (1 + gmean_day_return) ** (2 * annual_trading_days)
        )

        # Rate of return
        self.result.rate_of_return = (self.equity_history[-1] - self.equity_history[0]) / self.equity_history[0]

        # Measures with annualized returns and volatility
        self.result.sharpe_ratio = (self.result.annual_return - self.risk_free_rate) / self.result.annual_volatility
        self.result.sortino_ratio = (self.result.annual_return - self.risk_free_rate) / (
            np.sqrt(np.mean(day_returns.clip(-np.inf, 0) ** 2)) * np.sqrt(annual_trading_days)
        )
        self.result.risk_return_ratio = self.result.annual_return / (-self.result.avg_drawdown)

        # Benchmark-based measures
        # TODO: Calculate annualized measures with a single long-term trading history (using rolling window)
        close_df = self.candle_data.close.df().iloc[self.n_candles_to_skip :]
        close_df.index = self.dt_index
        symbol_day_returns = pd.DataFrame(
            {
                symbol: close_df[symbol].resample("D").last().dropna().pct_change()
                for symbol in self.candle_data.close.symbols
                if self.benchmark_symbol is None or symbol == self.benchmark_symbol
            }
        )
        benchmark_day_returns = symbol_day_returns.mean(axis=1)

        benchmark_up_return = benchmark_day_returns.where(benchmark_day_returns > 0, 0).mean()
        result_up_return = day_returns.where(benchmark_day_returns > 0, 0).mean()
        self.result.upside_capture_ratio = float(result_up_return / benchmark_up_return)

        benchmark_down_return = benchmark_day_returns.where(benchmark_day_returns < 0, 0).mean()
        result_down_return = day_returns.where(benchmark_day_returns < 0, 0).mean()
        self.result.downside_capture_ratio = float(result_down_return / (-benchmark_down_return))

        self.result.alpha = np.nanprod(1 + day_returns) - np.nanprod(1 + symbol_day_returns.values, axis=0).mean()
        self.result.beta = benchmark_day_returns.cov(day_returns) / float(np.var(benchmark_day_returns))

        # Stats per symbol
        symbols = set(symbol for strategy in self.strategies for symbol in strategy.symbols)
        for symbol in symbols:
            self.__compute_by_symbol(symbol)

        return self.result

    def __compute_by_symbol(self, symbol: Symbol) -> None:
        close_arr = self.candle_data.close[symbol][self.n_candles_to_skip :]
        self.result.positions[symbol] = [p for p in self.positions if p.symbol == symbol]
        self.result.trades[symbol] = [t for t in self.trades if t.symbol == symbol]
        self.result.buy_and_hold_return[symbol] = (close_arr[-1] - close_arr[0]) / close_arr[0]

        if not self.result.trades[symbol]:
            self.result.open_total[symbol] = 0
            self.result.realized_pnl[symbol] = 0
            self.result.fees[symbol] = 0
            self.result.ror_fee_included[symbol] = 0
            self.result.win_rate[symbol] = 0
            self.result.profit_factor[symbol] = -1
            self.result.exposure_time[symbol] = 0
            return

        self.result.open_total[symbol] = round(
            sum(p.averageOpenPrice * p.closedAmount for p in self.result.positions[symbol] if p.averageOpenPrice), 8
        )
        self.result.realized_pnl[symbol] = round(sum(t.realizedPnl for t in self.result.trades[symbol]), 8)
        self.result.fees[symbol] = -round(sum(t.fee.cost for t in self.result.trades[symbol]), 8)
        self.result.ror_fee_included[symbol] = round(
            (self.result.realized_pnl[symbol] + self.result.fees[symbol]) / self.result.open_total[symbol], 8
        )
        self.result.win_rate[symbol] = sum(t.realizedPnl > 0 for t in self.result.trades[symbol]) / len(
            self.result.trades[symbol]
        )

        sum_loss = sum(-t.realizedPnl for t in self.result.trades[symbol] if t.realizedPnl < 0)
        sum_profit = sum(t.realizedPnl for t in self.result.trades[symbol] if t.realizedPnl > 0)
        self.result.profit_factor[symbol] = (
            round(sum_profit / sum_loss, 8) if sum_loss > 0 else -1
        )  # avoid zero division error
        self.result.exposure_time[symbol] = sum(
            (p.closedTimestamp - p.timestamp) for p in self.result.positions[symbol] if p.closedTimestamp is not None
        ) / (1000 * 60 * 60)

    @staticmethod
    def compute_drawdown_duration(dd: pd.Series) -> pd.Series:
        iloc = np.unique(np.r_[(dd == 0).values.nonzero()[0], len(dd) - 1])  # type: ignore
        iloc = pd.Series(iloc, index=dd.index[iloc])
        df = iloc.to_frame("iloc").assign(prev=iloc.shift())
        df = df[df["iloc"] > df["prev"] + 1].astype(int)

        # If no drawdown since no trade, avoid below for pandas sake and return nan series
        if len(df) == 0:
            return dd.replace(0, np.nan)

        df["duration"] = df["iloc"].map(dd.index.__getitem__) - df["prev"].map(dd.index.__getitem__)
        df = df.reindex(dd.index)
        return df["duration"]

    @staticmethod
    def __geometric_mean(returns: pd.Series) -> float:
        returns = returns.fillna(0) + 1
        if np.any(returns <= 0):
            return 0
        return np.exp(np.log(returns).sum() / (len(returns) or np.nan)) - 1

    def __str__(self) -> str:
        stats = []
        for attr_name in self.__dict__:
            value = getattr(self, attr_name)
            if not callable(value):
                stats.append(f"{attr_name}: {value}")

        return "\n".join(stats)
