from datetime import datetime

from loguru import logger

from chartrider.core.common.repository.models import (
    ContingentOrder,
    OrderAction,
    OrderStatus,
)
from chartrider.core.strategy.base import EventDrivenStrategy
from chartrider.core.strategy.presets import StrategyPreset
from chartrider.utils.data import SymbolColumnData
from chartrider.utils.symbols import Symbol
from chartrider.utils.timeutils import TimeUtils

N_CANDLES_PER_DAY = 24 * 60


class SimpleVBsellonDeadCross(EventDrivenStrategy):
    def __init__(
        self,
        symbol: Symbol,
        holding_period: int = N_CANDLES_PER_DAY,  # minimum holding period in minutes
        k: float = 0.5,
        target_volatility: float = 0.05,
    ) -> None:
        super().__init__([symbol], candles_needed=15 * N_CANDLES_PER_DAY)
        self.symbol = symbol
        self.holding_period = holding_period
        self.k = k
        self.target_volatility = target_volatility

    @property
    def slug(self) -> str:
        return f"simplevbdc{self.symbol}"

    def setup(self) -> None:
        self.prev_range: float | None = None
        self.curr_range: float | None = None
        self.did_buy = False
        self.live_minute = None

    def update_indicators(self) -> None:
        self.sma12h = self.make_indicator(self.calculate_close_sma(n_candles=12 * 60))
        self.sma3 = self.make_indicator(self.calculate_close_sma(n_candles=3 * N_CANDLES_PER_DAY))
        self.sma5 = self.make_indicator(self.calculate_close_sma(n_candles=5 * N_CANDLES_PER_DAY))
        self.sma15 = self.make_indicator(self.calculate_close_sma(n_candles=15 * N_CANDLES_PER_DAY))
        self.range = self.make_indicator(self.calculate_range(n_candles=N_CANDLES_PER_DAY))

    def next(self):
        current_timestamp = self.current_timestamp
        this_minute = TimeUtils.timestamp_to_datetime(current_timestamp).minute
        if this_minute == self.live_minute:
            return
        else:
            self.live_minute = this_minute

        current_price = self.get_last_price(self.symbol)
        base_price = self.sma12h[self.symbol][-1]
        self.prev_range = self.range[self.symbol][-N_CANDLES_PER_DAY - 1] or None
        self.curr_range = self.range[self.symbol][-1] or None

        # skip if we don't have enough data
        if self.prev_range is None or self.curr_range is None or base_price is None:
            return

        if self.did_buy:
            if self.sma3[self.symbol][-1] < self.sma15[self.symbol][-1]:  # Dead cross
                for order in self.get_strategy_orders(self.symbol):
                    assert order.timestamp is not None  # FIXME: why is timestamp nullable?
                    if order.timestamp < current_timestamp - self.holding_period * 60 * 1000:
                        order_status = self.sync_order_status(order)

                        if order_status == OrderStatus.closed:
                            self.liquidate_order(order)
                            continue

                        if order_status == OrderStatus.open:
                            self.cancel_order(order)
                            continue

            if len(self.strategy_orders[self.symbol]) == 0:
                self.did_buy = False
            return

        hit_target_price = current_price >= base_price + self.curr_range * self.k

        if (
            hit_target_price
            and self.sma15[self.symbol][-1] < current_price
            and self.sma5[self.symbol][-1] < current_price
            and self.sma3[self.symbol][-1] < current_price
        ):
            prev_volatility = self.prev_range / current_price
            invest_proportion = min(0.95, self.target_volatility / prev_volatility)
            balance = self.balance.totalWalletBalance / self.broker.registered_strategies_count
            amount = min(invest_proportion * balance, self.balance.availableBalance) / current_price

            order = self.place_order(
                symbol=self.symbol,
                action=OrderAction.open_long,
                amount=amount,
                price=current_price,
                contingent_sl=ContingentOrder(triggerPrice=current_price * 0.95),
            )

            if order is not None:
                self.signposter.emit_event(
                    name="SimpleVB: Buy",
                    timestamp=current_timestamp,
                    amount=amount,
                    invest_proportion=invest_proportion,
                )
                self.did_buy = True

                def reset_did_buy_on_sltp(order_id: str):
                    logger.info(f"Resetting did_buy for order {order_id}")
                    self.did_buy = False

                self.event_monitor.did_liquidate_by_contingent.subscribe(order.id, reset_did_buy_on_sltp)

    def calculate_close_sma(self, n_candles: int) -> SymbolColumnData:
        sma_df = self.candle_data.close.df(self.symbols).rolling(n_candles).mean()
        return SymbolColumnData.from_dataframe(sma_df)

    def calculate_range(self, n_candles: int) -> SymbolColumnData:
        high_max = self.candle_data.high.df(self.symbols).rolling(n_candles).max()
        low_min = self.candle_data.low.df(self.symbols).rolling(n_candles).min()
        return SymbolColumnData.from_dataframe((high_max - low_min).round(decimals=6))


presets: list[StrategyPreset] = [
    StrategyPreset(
        name="SimpleVBsellonDeadCross (BTC)",
        description="VB without timeframe diversification, sell on dead cross",
        strategies=[SimpleVBsellonDeadCross(symbol=Symbol.BTC)],
    ),
    StrategyPreset(
        name="SimpleVBsellonDeadCross (BTC and ETH)",
        description="VB without timeframe diversification, sell on dead cross",
        strategies=[SimpleVBsellonDeadCross(symbol=symbol) for symbol in [Symbol.BTC, Symbol.ETH]],
    ),
    StrategyPreset(
        name="SimpleVBsellonDeadCross (Top10)",
        description="VB without timeframe diversification, sell on dead cross",
        strategies=[SimpleVBsellonDeadCross(symbol=symbol) for symbol in Symbol.top10()],
    ),
    StrategyPreset(
        name="SimpleVBsellonDeadCross (All)",
        description="VB without timeframe diversification, sell on dead cross",
        strategies=[SimpleVBsellonDeadCross(symbol=symbol) for symbol in Symbol.all()],
    ),
]

if __name__ == "__main__":
    from chartrider.core.backtest.execution.builder import build_handler_from_preset

    debug_preset = StrategyPreset(
        name="SimpleVBsellonDeadCross (Debug)",
        strategies=[SimpleVBsellonDeadCross(symbol=symbol) for symbol in [Symbol.BTC]],
    )
    handler = build_handler_from_preset(
        start=datetime(2023, 1, 1), end=datetime(2024, 2, 24), strategy_preset=debug_preset
    )
    handler.run()
