from datetime import datetime
from typing import cast

import pandas as pd

from chartrider.core.strategy.base import RebalancingStrategy
from chartrider.core.strategy.presets import StrategyPreset
from chartrider.utils.data import SymbolColumnData
from chartrider.utils.symbols import Symbol
from chartrider.utils.timeutils import TimeUtils

N_CANDLES_PER_DAY = 24 * 60


class RSIMultiAsset(RebalancingStrategy):
    def __init__(
        self,
        symbols: list[Symbol],
        h_rsi_z_thres: float = 1.96,
        liq_thres: float = 0.3,
        rank_power: float = 3.0,
        invest_ratio: float = 0.9,
    ) -> None:
        super().__init__(symbols, candles_needed=2 * N_CANDLES_PER_DAY)
        self.h_rsi_thres = h_rsi_z_thres
        self.liq_thres = liq_thres
        self.rank_power = rank_power
        self.invest_ratio = invest_ratio

    @property
    def slug(self) -> str:
        return f"rsima{len(self.symbols)}symbols"

    def setup(self) -> None:
        self.did_buy = False
        self.hit_hours: set[datetime] = set()

    def update_indicators(self) -> None:  ## TODO: Should calculate daily values
        self.d_rsi = self.make_indicator(self.calculate_rsi(n_rolling=N_CANDLES_PER_DAY), name="daily_rsi", plot=True)
        self.h_rsi = self.make_indicator(self.calculate_rsi(n_rolling=60), name="hourly_rsi", plot=True)

        # hourly liquidity
        self.h_liq = self.make_indicator(self.calculate_liquidity(n_rolling=60), name="hourly_liq", plot=True)

        # rank of the horuly liquidity
        # FIXME: This is too ugly
        _h_liq_df = self.h_liq.original_indicator.df()
        h_liq_rank = _h_liq_df.apply(lambda x: (x.rank() - 1) / (len(x) - x.isna().sum() - 1), axis=1)
        self.h_liq_rank = self.make_indicator(
            self.identity_indicator(df=cast(pd.DataFrame, h_liq_rank)), name="hourly_liq_rank", plot=True
        )

        _h_rsi_df = self.h_rsi.original_indicator.df()
        _h_liq_rank_df = self.h_liq_rank.original_indicator.df()
        self.mask = self.make_indicator(
            self.calculate_mask(h_rsi=_h_rsi_df, n_rolling=24, h_liq_rank=_h_liq_rank_df),
            name="mask",
            plot=True,
        )

        # rank of the daily rsi
        # FIXME: This is too ugly
        _d_rsi_df = self.d_rsi.original_indicator.df()
        d_rank = _d_rsi_df.apply(lambda x: (x.rank() - 1) / (len(x) - x.isna().sum() - 1), axis=1) ** self.rank_power
        self.d_rank = self.make_indicator(
            self.identity_indicator(df=cast(pd.DataFrame, d_rank)), name="daily_rsi_rank", plot=True
        )

    def next(self):
        this_datetime = TimeUtils.timestamp_to_datetime(self.current_timestamp, truncate_to_minutes=True)

        if this_datetime.minute != 0:
            return

        d_rank = self.d_rank.resized_indicator.get_last()

        # Get the current position of this strategy
        sum_rank = sum(d_rank)

        current_prices = self.broker.candle_data.close.get_last()

        invest_amount = self.balance.totalWalletBalance * self.invest_ratio
        new_positions = {
            symbol: invest_amount / p * (r / sum_rank)
            for symbol, r, p in zip(self.d_rank.resized_indicator.symbols, d_rank, current_prices)
        }
        self.rebalance(new_positions)

    def calculate_rsi(self, n_rolling: int) -> SymbolColumnData:
        close_diff = self.candle_data.close.df(self.symbols).diff(1)
        gain = close_diff.where(close_diff > 0, 0).rolling(n_rolling).sum()
        loss = -close_diff.where(close_diff < 0, 0).rolling(n_rolling).sum()
        return SymbolColumnData.from_dataframe(gain / loss)

    def calculate_liquidity(self, n_rolling: int) -> SymbolColumnData:
        volume = self.candle_data.volume.df(self.symbols).rolling(n_rolling).sum()
        close = self.candle_data.close.df(self.symbols)
        return SymbolColumnData.from_dataframe(volume * close / n_rolling)

    def calculate_mask(self, h_rsi: pd.DataFrame, n_rolling: int, h_liq_rank: pd.DataFrame) -> SymbolColumnData:
        h_rsi_zscore = (h_rsi - h_rsi.rolling(n_rolling).mean()) / h_rsi.rolling(n_rolling).std()
        h_rsi_mask = h_rsi_zscore > self.h_rsi_thres
        h_liq_mask = h_liq_rank > self.liq_thres
        return SymbolColumnData.from_dataframe(h_rsi_mask & h_liq_mask)

    def identity_indicator(self, df: pd.DataFrame) -> SymbolColumnData:
        return SymbolColumnData.from_dataframe(df)


presets: list[StrategyPreset] = [
    StrategyPreset(
        name="Daily RSI Long (BTC, ETH)",
        description="Buy when daily RSI > cutoff",
        strategies=[RSIMultiAsset(symbols=[Symbol.BTC, Symbol.ETH])],
    ),
    StrategyPreset(
        name="Daily RSI Long (Top10)",
        description="Buy when daily RSI > cutoff",
        strategies=[RSIMultiAsset(symbols=Symbol.top10())],
    ),
]


if __name__ == "__main__":
    from chartrider.core.backtest.execution.builder import build_handler_from_preset

    debug_preset = StrategyPreset(
        name="Debug",
        strategies=[RSIMultiAsset(symbols=Symbol.top10(), invest_ratio=0.95)],
    )
    handler = build_handler_from_preset(
        start=datetime(2023, 1, 1), end=datetime(2023, 7, 1), strategy_preset=debug_preset
    )
    handler.run()
