import pickle
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import click
import numpy as np
import pandas as pd

from chartrider.analysis.datasource import (
    PlotDataSource,
    StrategyDataSource,
    SymbolDataSource,
)
from chartrider.analysis.stat import StatAnalyzer, StatResult
from chartrider.core.backtest.broker import BacktestBroker
from chartrider.core.backtest.repository import BacktestRepository
from chartrider.core.common.repository.models import (
    ClientOrderId,
    OrderAction,
    PositionSide,
    Trade,
)
from chartrider.core.strategy.base import BaseStrategy
from chartrider.settings import BACKTEST_REPORTS_PATH
from chartrider.utils.data import Indicator
from chartrider.utils.symbols import Symbol
from chartrider.utils.textsanitizer import get_valid_filename
from chartrider.utils.timeutils import TimeUtils

if TYPE_CHECKING:
    from chartrider.core.backtest.execution.handler import BacktestExecutionHandler


class BacktestPostprocessor:
    """
    Post-processes backtest results by generating statistics and plots.
    Handles saving to directories and updating leaderboards.
    """

    def __init__(self, execution_handler: "BacktestExecutionHandler") -> None:
        self.execution_handler = execution_handler
        self.__prepare_file_dir()

    @property
    def broker(self) -> BacktestBroker:
        return self.execution_handler.broker

    @property
    def repository(self) -> BacktestRepository:
        return self.broker.repository

    @property
    def period_string(self) -> str:
        start = self.execution_handler.start
        end = self.execution_handler.end
        return f"{start.strftime('%Y%m%d')}-{end.strftime('%Y%m%d')}"

    @property
    def leaderboard_file_path(self) -> Path:
        return BACKTEST_REPORTS_PATH / self.period_string / "leaderboard.csv"

    @property
    def report_file_name(self) -> str:
        datestring = TimeUtils.timestamp_to_datestring(TimeUtils.timestamp_in_ms(), compact=True)
        datestring = datestring.replace(" ", ".")
        filename = f"{datestring}_{self.preset_name}"
        return get_valid_filename(filename)

    @property
    def report_file_path(self) -> Path:
        return BACKTEST_REPORTS_PATH / self.period_string / self.report_file_name

    def __prepare_file_dir(self):
        self.leaderboard_file_path.parent.mkdir(parents=True, exist_ok=True)
        self.report_file_path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def preset_name(self) -> str:
        return self.execution_handler.strategy_preset.name

    def process(self) -> None:
        stat_result = self.__prepare_stats()
        click.echo(stat_result.format())
        self.__update_leaderboard(stat_result)
        self.__save_plot_data(stat_result)

    def __save_plot_data(self, stat_result: StatResult) -> None:
        factory = PlotDataSourceFactory(self.execution_handler)
        datasource = factory.make_plot_datasource(stat_result)

        with open(f"{self.report_file_path}.pkl", "wb") as f:
            pickle.dump(datasource, f)

    def __prepare_stats(self) -> StatResult:
        analyzer = StatAnalyzer(
            n_candles_to_skip=self.broker.max_candles_needed,
            strategies=self.execution_handler.strategies,
            candle_data=self.broker.candle_data,
            trades=self.broker.repository.fetch_trades(),
            positions=self.broker.repository.fetch_closed_positions(),
            equity_history=self.broker.equity_history,
        )
        result = analyzer.compute()
        return result

    def __update_leaderboard(self, result: StatResult) -> None:
        lb_columns = {
            "rate_of_return": "Return [%]",
            "annual_return": "Ann. Return [%]",
            "annual_volatility": "Ann. Volat. [%]",
            "max_drawdown": "Max. DD [%]",
            "avg_drawdown": "Avg. DD [%]",
            "max_drawdown_duration": "Max. DD Dur.",
            "avg_drawdown_duration": "Avg. DD Dur.",
            "sharpe_ratio": "Sharpe Ratio",
            "sortino_ratio": "Sortino Ratio",
            "risk_return_ratio": "Risk Return Ratio",
            "upside_capture_ratio": "Upside Capture Ratio",
            "downside_capture_ratio": "Downside Capture Ratio",
            "beta": "Beta",
            "alpha": "Alpha",
            "num_trades": "Num. Trades",
            "created_at": "Created At",
        }

        if not self.leaderboard_file_path.exists():
            df = pd.DataFrame(columns=list(lb_columns.values()))
            df.index.name = "Name"
        else:
            df = pd.read_csv(self.leaderboard_file_path, index_col="Name")

        for attr, col in lb_columns.items():
            value = getattr(result, attr)
            if isinstance(value, float):
                if col.endswith("[%]"):
                    value *= 100
                    value = round(value, 2)
                else:
                    value = round(value, 4)
            df.loc[self.preset_name, col] = value  # type: ignore

        df.sort_values(by="Sharpe Ratio", ascending=False, inplace=True)
        df.to_csv(self.leaderboard_file_path, float_format="%.8f", index=True)


class PlotDataSourceFactory:
    def __init__(self, execution_handler: "BacktestExecutionHandler") -> None:
        self.execution_handler = execution_handler

    def make_plot_datasource(self, stat_result: StatResult) -> PlotDataSource:
        preset = self.execution_handler.strategy_preset
        return PlotDataSource(
            id=uuid4(),
            name=preset.name,
            description=preset.description,
            equity_history=self.execution_handler.broker.equity_history,
            strategy_sources=self.__make_strategy_datasources(),
            stat=stat_result,
        )

    def __make_strategy_datasources(self) -> list[StrategyDataSource]:
        strategies = self.execution_handler.strategies
        return [self.__make_strategy_datasource(strategy) for strategy in strategies]

    def __make_strategy_datasource(self, strategy: BaseStrategy) -> StrategyDataSource:
        all_orders = [
            order
            for symbol in strategy.symbols
            for order in self.execution_handler.broker.repository.fetch_orders(symbol)
        ]
        strategy_orders = [
            order
            for order in all_orders
            if isinstance(order.clientOrderId, ClientOrderId) and order.clientOrderId.strategy == strategy.slug
        ]
        signposts = strategy.signposter.get_signposts()
        strategy_trades = [trade for order in strategy_orders for trade in order.trades]
        long_trades = [
            trade for order in strategy_orders for trade in order.trades if order.orderAction.positionSide.isLong
        ]
        short_trades = [
            trade for order in strategy_orders for trade in order.trades if order.orderAction.positionSide.isShort
        ]
        indicators = self.__extract_indicators(strategy)
        return StrategyDataSource(
            id=uuid4(),
            strategy_name=strategy.__class__.__name__,
            strategy_slug=strategy.slug,
            orders=strategy_orders,
            trades=strategy_trades,
            long_trades=long_trades,
            short_trades=short_trades,
            indicators=indicators,
            symbol_sources=self.__make_symbol_datasources(strategy, long_trades, short_trades),
            signposts=signposts,
        )

    def __extract_indicators(self, strategy: BaseStrategy) -> list[Indicator]:
        indicators = []
        for indicator in strategy.__dict__.values():
            if isinstance(indicator, Indicator):
                indicators.append(indicator)
        return indicators

    def __make_symbol_datasources(
        self,
        strategy: BaseStrategy,
        long_trades: list[Trade],
        short_trades: list[Trade],
    ) -> list[SymbolDataSource]:
        symbol_datasources = []
        for symbol in strategy.symbols:
            position_history = self.__prepare_position_history_data(
                symbol=symbol,
                long_trades=long_trades,
                short_trades=short_trades,
                close=strategy.broker.candle_data.close[symbol].as_array(),
                timestamp=strategy.broker.candle_data.timestamp_array,
            )
            symbol_datasources.append(
                SymbolDataSource(
                    id=uuid4(),
                    symbol=symbol,
                    open=strategy.broker.candle_data.open[symbol].as_array(),
                    high=strategy.broker.candle_data.high[symbol].as_array(),
                    low=strategy.broker.candle_data.low[symbol].as_array(),
                    close=strategy.broker.candle_data.close[symbol].as_array(),
                    volume=strategy.broker.candle_data.volume[symbol].as_array(),
                    timestamp=strategy.broker.candle_data.timestamp_array,
                    long_amount_history=position_history["long_amount"].to_numpy(),
                    short_amount_history=position_history["short_amount"].to_numpy(),
                    long_notional_history=position_history["long_notional"].to_numpy(),
                    short_notional_history=position_history["short_notional"].to_numpy(),
                )
            )
        return symbol_datasources

    def __prepare_position_history_data(
        self,
        symbol: Symbol,
        long_trades: list[Trade],
        short_trades: list[Trade],
        close: np.ndarray,
        timestamp: np.ndarray,
    ) -> pd.DataFrame:
        """
        Prepares historical open position data by computing the cumulative sum of
        long and short trade amounts and calculating notional values for each position.

        Returns:
            pd.DataFrame: A DataFrame indexed by timestamp with the following columns:
                          - 'long_amount': Amount of opened long positions.
                          - 'short_amount': Amount of opened short positions.
                          - 'long_notional': Notional value of opened long positions.
                          - 'short_notional': Notional value of opened short positions.
        """
        cumsum_df = pd.DataFrame(0, index=timestamp, columns=["long_amount", "short_amount"])

        def prepare_cumsum_df(long_or_short_trades: list[Trade], side: PositionSide):
            amount_column_name = f"{side}_amount".lower()
            for trade in long_or_short_trades:
                if trade.symbol != symbol:
                    continue
                order_action = OrderAction.from_side(trade.side, position_side=side)
                trade_amount = float(trade.amount)
                if order_action.isClosing:
                    trade_amount *= -1
                cumsum_df.at[trade.timestamp, amount_column_name] += float(trade_amount)
            # Reconstruct position history from individual trades
            cumsum_df[amount_column_name] = cumsum_df[amount_column_name].cumsum()

        prepare_cumsum_df(long_trades, PositionSide.long)
        prepare_cumsum_df(short_trades, PositionSide.short)

        # Calculate notional prices for long and short positions
        cumsum_df["long_notional"] = cumsum_df["long_amount"] * close
        cumsum_df["short_notional"] = cumsum_df["short_amount"] * close
        return cumsum_df
