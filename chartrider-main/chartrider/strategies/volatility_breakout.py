from datetime import datetime
from textwrap import dedent

from loguru import logger

from chartrider.core.common.repository.models import ContingentOrder, OrderAction
from chartrider.core.strategy.base import EventDrivenStrategy
from chartrider.core.strategy.presets import StrategyPreset
from chartrider.utils.data import SymbolColumnData
from chartrider.utils.symbols import Symbol
from chartrider.utils.timeutils import TimeUtils

N_CANDLES_PER_DAY = 24 * 60


class VolatilityBreakout(EventDrivenStrategy):
    def __init__(
        self,
        symbol: Symbol,
        reference_hour: int = 0,
        k: float = 0.5,
        target_volatility: float = 0.05,
    ) -> None:
        super().__init__([symbol], candles_needed=15 * N_CANDLES_PER_DAY)
        self.symbol = symbol
        self.reference_hour = reference_hour
        self.k = k
        self.target_volatility = target_volatility

    @property
    def slug(self) -> str:
        return f"vb{self.reference_hour}{self.symbol}"

    def setup(self) -> None:
        self.prev_range: float | None = None
        self.curr_range: float | None = None
        self.starting_price: float | None = None
        self.did_buy = False

        # in live trading, reference hour can be hit multiple times
        # so we need to keep track of the hours we've hit
        self.hit_hours: set[datetime] = set()  # FIXME: where to place this?

    def update_indicators(self) -> None:
        should_plot = True if self.reference_hour == 0 else False

        self.sma3 = self.make_indicator(self.calculate_close_sma(n_candles=3 * N_CANDLES_PER_DAY), plot=should_plot)
        self.sma5 = self.make_indicator(self.calculate_close_sma(n_candles=5 * N_CANDLES_PER_DAY), plot=should_plot)
        self.sma15 = self.make_indicator(self.calculate_close_sma(n_candles=15 * N_CANDLES_PER_DAY), plot=should_plot)
        self.range = self.make_indicator(self.calculate_range(n_candles=N_CANDLES_PER_DAY), plot=should_plot)

    def next(self):
        current_price = self.get_last_price(self.symbol)
        this_datetime = TimeUtils.timestamp_to_datetime(self.current_timestamp, truncate_to_minutes=True)

        if (
            this_datetime not in self.hit_hours
            and this_datetime.hour == self.reference_hour
            and this_datetime.minute == 0
        ):
            self.hit_hours.add(this_datetime)
            self.clear_all()
            self.starting_price = current_price
            self.prev_range = self.range[self.symbol][-N_CANDLES_PER_DAY - 1]
            self.curr_range = self.range[self.symbol][-1]
            self.did_buy = False
            logger.info(
                dedent(
                    f"""
                    Hit reference hour, liquidating all orders and resetting indicators.
                    <pre>
                    Reference hour: {self.reference_hour}
                    Datetime: {this_datetime}
                    Current price: {current_price}
                    Current range: {self.curr_range}
                    Target price: {self.starting_price + (self.curr_range or 0) * self.k}
                    </pre>
                    """
                )
            )

        # skip if we don't have enough data
        if self.curr_range is None or self.starting_price is None or self.prev_range is None:
            return

        # skip if we already bought during the last 24 hours
        if self.did_buy:
            return

        hit_target_price = current_price >= self.starting_price + self.curr_range * self.k

        if (
            hit_target_price
            and self.sma15[self.symbol][-1] < current_price
            and self.sma5[self.symbol][-1] < current_price
            and self.sma3[self.symbol][-1] < current_price
        ):
            prev_volatility = self.prev_range / current_price
            invest_proportion = min(0.99, (self.target_volatility / prev_volatility))
            balance = self.balance.totalWalletBalance / self.broker.registered_strategies_count
            amount = min(invest_proportion * balance, self.balance.availableBalance) / (
                current_price / self.broker.repository.get_leverage(self.symbol)
            )

            _ = self.place_order(
                symbol=self.symbol,
                action=OrderAction.open_long,
                amount=amount,
                price=current_price,
                contingent_sl=ContingentOrder(triggerPrice=current_price * 0.95),
            )

            # Don't keep trying even if it somehow failed to create an order.
            self.did_buy = True

            logger.info(
                dedent(
                    f"""
                    Target price hit and SMA conditions met, buying.

                    <pre>
                    Reference hour: {self.reference_hour}
                    Datetime: {this_datetime}
                    Current price: {current_price}
                    Target price: {self.starting_price + self.curr_range * self.k}
                    SMA3: {self.sma3[self.symbol][-1]}
                    SMA5: {self.sma5[self.symbol][-1]}
                    SMA10: {self.sma15[self.symbol][-1]}
                    Invest proportion: {invest_proportion}
                    </pre>
                    """
                )
            )
        elif hit_target_price:
            logger.debug(
                dedent(
                    f"""
                    Target price hit but SMA conditions not met.
                    <pre>
                    Reference hour: {self.reference_hour}
                    Datetime: {this_datetime}
                    Current price: {current_price}
                    Target price: {self.starting_price + self.curr_range * self.k}
                    SMA3: {self.sma3[self.symbol][-1]}
                    SMA5: {self.sma5[self.symbol][-1]}
                    SMA10: {self.sma15[self.symbol][-1]}
                    </pre>
                    """
                )
            )

    def calculate_close_sma(self, n_candles: int) -> SymbolColumnData:
        sma_df = self.candle_data.close.df(self.symbols).rolling(n_candles).mean()
        return SymbolColumnData.from_dataframe(sma_df)

    def calculate_range(self, n_candles: int) -> SymbolColumnData:
        high_max = self.candle_data.high.df(self.symbols).rolling(n_candles).max()
        low_min = self.candle_data.low.df(self.symbols).rolling(n_candles).min()
        return SymbolColumnData.from_dataframe((high_max - low_min).round(decimals=6))


presets: list[StrategyPreset] = [
    StrategyPreset(
        name="Volatility Breakout 24H (BTC)",
        description="Perform a volatility breakout strategy every hour of the day.",
        strategies=[VolatilityBreakout(symbol=Symbol.BTC, reference_hour=h) for h in range(24)],
    ),
    # The following presets are commented out because they are too slow to backtest.
    # StrategyPreset(
    #     name="Volatility Breakout 24H (Top10)",
    #     description="Perform a volatility breakout strategy every hour of the day.",
    #     strategies=[
    #         VolatilityBreakout(symbol=symbol, reference_hour=h) for h in range(24) for symbol in Symbol.top7()
    #     ],
    # ),
    # StrategyPreset(
    #     name="Volatility Breakout 24H (All)",
    #     description="Perform a volatility breakout strategy every hour of the day.",
    #     strategies=[
    #         VolatilityBreakout(symbol=symbol, reference_hour=h) for h in range(24) for symbol in Symbol.all()
    #     ],
    # ),
]

if __name__ == "__main__":
    from chartrider.core.backtest.execution.builder import build_handler_from_preset

    debug_preset = StrategyPreset(
        name="Volatility Breakout (Debug)",
        strategies=[VolatilityBreakout(symbol=Symbol.BTC, reference_hour=h) for h in range(2)],
    )
    handler = build_handler_from_preset(
        start=datetime(2023, 1, 1), end=datetime(2024, 2, 24), strategy_preset=debug_preset
    )

    handler.run()
