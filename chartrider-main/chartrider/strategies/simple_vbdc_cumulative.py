from datetime import datetime

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


class SimpleVBDCCumulative(EventDrivenStrategy):
    def __init__(
        self,
        symbol: Symbol,
        holding_period: int = N_CANDLES_PER_DAY // 6,  # minimum holding period in minutes
        buy_interval: int = N_CANDLES_PER_DAY // 12,  # minimum interval between buys in minutes
        k: float = 0.6,
        max_invest_proportion: float = 0.1,  # maximum proportion of the balance to invest
        leverage: int = 8,
    ) -> None:
        super().__init__([symbol], candles_needed=20 * N_CANDLES_PER_DAY)
        self.symbol = symbol
        self.holding_period = holding_period
        self.buy_interval = buy_interval
        self.k = k
        self.max_invest_proportion = max_invest_proportion
        self.leverage = leverage

    @property
    def slug(self) -> str:
        return f"simplevbdccum{self.symbol}"

    def setup(self) -> None:
        self.curr_range: float | None = None
        self.did_buy = False
        self.ready_to_buy = True
        self.broker.repository.set_leverage(self.symbol, self.leverage)
        self.last_executed_minute = None

    def update_indicators(self) -> None:
        base_dur = N_CANDLES_PER_DAY // 24 * 30  # 30 hours

        self.sma_1 = self.make_indicator(self.calculate_close_sma(n_candles=base_dur // 2))
        self.sma_2 = self.make_indicator(self.calculate_close_sma(n_candles=base_dur * 3))
        self.sma_3 = self.make_indicator(self.calculate_close_sma(n_candles=base_dur * 5))
        self.sma_4 = self.make_indicator(self.calculate_close_sma(n_candles=base_dur * 15))
        self.range = self.make_indicator(self.calculate_range(n_candles=base_dur))

    def next(self):
        current_timestamp = self.current_timestamp
        this_minute = TimeUtils.timestamp_to_datetime(current_timestamp).minute
        if this_minute == self.last_executed_minute:
            return
        else:
            self.last_executed_minute = this_minute

        current_price = self.get_last_price(self.symbol)
        base_price = self.sma_1[self.symbol][-1]
        self.curr_range = self.range[self.symbol][-1] or None

        # skip if we don't have enough data
        if self.curr_range is None or base_price is None:
            return

        if self.did_buy:
            self.ready_to_buy = True
            for order in self.get_strategy_orders(self.symbol):
                assert order.timestamp is not None  # FIXME: why is timestamp nullable?
                if order.timestamp < current_timestamp - self.holding_period * 60 * 1000:
                    if self.sma_1[self.symbol][-1] < self.sma_3[self.symbol][-1]:  # Dead cross
                        order_status = self.sync_order_status(order)

                        if order_status == OrderStatus.closed:
                            self.liquidate_order(order)
                            continue

                        if order_status == OrderStatus.open:
                            self.cancel_order(order)
                            continue
                if order.timestamp > current_timestamp - self.buy_interval * 60 * 1000:
                    # If it is within the `buy_interval` since the last order was created,
                    # we're not ready to buy more.
                    self.ready_to_buy = False

            if len(self.strategy_orders[self.symbol]) == 0:
                self.did_buy = False

            if not self.ready_to_buy:
                return

        hit_target_price = current_price >= base_price + self.curr_range * self.k

        if (
            hit_target_price
            and self.sma_4[self.symbol][-1] < current_price
            and self.sma_3[self.symbol][-1] < current_price
            and self.sma_2[self.symbol][-1] < current_price
            and self.sma_4[self.symbol][-1] < self.sma_2[self.symbol][-1]
        ):
            balance = self.balance.totalWalletBalance / self.broker.registered_strategies_count
            # TODO: use CLV to determine the amount to buy
            invest_proportion = self.max_invest_proportion * max(0.4, (0.8 ** len(self.strategy_orders[self.symbol])))
            notional = min(invest_proportion * balance, self.balance.availableBalance) * self.leverage
            notional *= 0.99  # consider fees and slippage
            amount = notional / current_price

            order = self.place_order(
                symbol=self.symbol,
                action=OrderAction.open_long,
                amount=amount,
                price=current_price,
                contingent_sl=ContingentOrder(triggerPrice=current_price * 0.975),  # 2.5% stop loss
            )

            if order is not None:
                self.signposter.emit_event(
                    name="SimpleVBDCCumulative: Buy",
                    timestamp=current_timestamp,
                    amount=amount,
                    invest_proportion=invest_proportion,
                    leverage=self.leverage,
                )
                self.did_buy = True

    def calculate_close_sma(self, n_candles: int) -> SymbolColumnData:
        sma_df = self.candle_data.close.df(self.symbols).rolling(n_candles).mean()
        return SymbolColumnData.from_dataframe(sma_df)

    def calculate_range(self, n_candles: int) -> SymbolColumnData:
        high_max = self.candle_data.high.df(self.symbols).rolling(n_candles).max()
        low_min = self.candle_data.low.df(self.symbols).rolling(n_candles).min()
        return SymbolColumnData.from_dataframe((high_max - low_min).round(decimals=6))


presets: list[StrategyPreset] = [
    StrategyPreset(
        name="SimpleVBDCCumulative (BTC)",
        description="VB without timeframe diversification, sell on dead cross, cumulative mode",
        strategies=[SimpleVBDCCumulative(symbol=Symbol.BTC)],
    ),
    StrategyPreset(
        name="SimpleVBDCCumulative (BTC and ETH)",
        description="VB without timeframe diversification, sell on dead cross, cumulative mode",
        strategies=[SimpleVBDCCumulative(symbol=symbol) for symbol in [Symbol.BTC, Symbol.ETH]],
    ),
    # StrategyPreset(
    #     name="SimpleVBDCCumulative (Top10)",
    #     description="VB without timeframe diversification, sell on dead cross, cumulative mode",
    #     strategies=[SimpleVBDCCumulative(symbol=symbol) for symbol in Symbol.top10()],
    # ),
    # StrategyPreset(
    #     name="SimpleVBDCCumulative (All)",
    #     description="VB without timeframe diversification, sell on dead cross, cumulative mode",
    #     strategies=[SimpleVBDCCumulative(symbol=symbol) for symbol in Symbol.all()],
    # ),
]

if __name__ == "__main__":
    from chartrider.core.backtest.execution.builder import build_handler_from_preset

    debug_preset = StrategyPreset(
        name="SimpleVBDCCumulative (Debug)",
        strategies=[SimpleVBDCCumulative(symbol=symbol) for symbol in [Symbol.BTC, Symbol.ETH]],
    )
    handler = build_handler_from_preset(
        start=datetime(2022, 1, 1), end=datetime(2024, 4, 21), strategy_preset=debug_preset
    )
    handler.run()
