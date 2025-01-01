import random
from datetime import datetime

from loguru import logger

from chartrider.core.common.repository.models import (
    ContingentOrder,
    OrderAction,
    OrderStatus,
)
from chartrider.core.strategy.base import EventDrivenStrategy
from chartrider.core.strategy.presets import StrategyPreset
from chartrider.utils.symbols import Symbol


class RandomBuy(EventDrivenStrategy):
    def __init__(self, symbol: Symbol) -> None:
        super().__init__([symbol], candles_needed=10000)
        self.symbol = symbol

    @property
    def slug(self) -> str:
        return f"random{self.symbol.base_currency}"

    def setup(self) -> None:
        pass

    def update_indicators(self) -> None:
        pass

    def next(self):
        current_price = self.get_last_price(self.symbol)

        if random.random() < 0.99:
            # do nothing most of the time
            return

        if random.random() < 0.9:
            orders = self.get_strategy_orders(self.symbol)
            if not orders:
                return
            order = random.choice(list(orders))

            if order.status == OrderStatus.closed:
                self.liquidate_order(order)
                return

            if order.status == OrderStatus.open:
                self.cancel_order(order)
                return

            return

        action = random.choice([OrderAction.open_long, OrderAction.open_short])
        amount = (random.random() / 10) * (self.balance.totalWalletBalance / current_price)
        price = current_price * random.choice([1.01, 0.99])  # may induce slippage
        contingent_sl = (
            ContingentOrder(triggerPrice=price * 0.9)
            if action == OrderAction.open_long
            else ContingentOrder(triggerPrice=price * 1.1)
        )

        logger.debug(f"Creating {self.symbol} order: {action}, price: {price}, amount: {amount}")
        self.place_order(symbol=self.symbol, action=action, amount=amount, price=price, contingent_sl=contingent_sl)


presets: list[StrategyPreset] = [
    StrategyPreset(
        name="RandomBuy (BTC)",
        description="Just a random buy/sell strategy for BTCUSDT.",
        strategies=[RandomBuy(symbol=Symbol.BTC)],
    )
]


if __name__ == "__main__":
    from chartrider.core.backtest.execution.builder import build_handler_from_preset

    debug_preset = StrategyPreset(
        name="RandomBuy (Debug)",
        strategies=[RandomBuy(symbol=Symbol.BTC), RandomBuy(symbol=Symbol.ETH)],
    )
    handler = build_handler_from_preset(
        start=datetime(2023, 12, 1), end=datetime(2024, 1, 1), strategy_preset=debug_preset
    )
    handler.run()
