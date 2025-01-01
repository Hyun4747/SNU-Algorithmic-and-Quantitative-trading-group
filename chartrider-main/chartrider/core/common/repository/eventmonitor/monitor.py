import asyncio
from collections import defaultdict
from typing import Any, Protocol

import ccxt.pro
from loguru import logger

from chartrider.core.common.repository.models import (
    Order,
    OrderStatus,
    OrderType,
    PositionSide,
)
from chartrider.utils.symbols import Symbol


class AnyOrderEventCallback(Protocol):
    def __call__(self, order_id: str) -> None:
        ...


class LiquidationEventCallback(Protocol):
    def __call__(self, symbol: Symbol, side: PositionSide) -> None:
        ...


class OrderEventPublisher:
    def __init__(self) -> None:
        self.__callbacks: dict[str, list[AnyOrderEventCallback]] = defaultdict(list)

    def subscribe(self, order_id: str, callback: AnyOrderEventCallback):
        self.__callbacks[order_id].append(callback)

    def publish(self, order_id: str):
        for callback in self.__callbacks[order_id]:
            callback(order_id)

        self.__callbacks[order_id].clear()


class ForceLiquidationEventPublisher:
    def __init__(self) -> None:
        self.__callbacks: list[LiquidationEventCallback] = []

    def subscribe(self, callback: LiquidationEventCallback):
        self.__callbacks.append(callback)

    def publish(self, liquidation_order: Order):
        symbol = liquidation_order.symbol
        position_side = liquidation_order.positionSide
        for callback in self.__callbacks:
            callback(symbol, position_side)


class EventMonitor:
    def __init__(self, exchange: ccxt.pro.binanceusdm | None) -> None:
        self.__exchange = exchange

        self.did_liquidate_by_contingent = OrderEventPublisher()
        self.did_force_liquidate = ForceLiquidationEventPublisher()
        self.did_close = OrderEventPublisher()

    async def watch_orders(self, main_loop: asyncio.AbstractEventLoop):
        assert self.__exchange is not None, "Exchange is not configured."
        while True:
            try:
                orders_data: list[Any] = await self.__exchange.watch_orders()
                orders = [Order(**order) for order in orders_data]
                for order in orders:
                    if order.status != OrderStatus.closed:
                        continue
                    main_loop.call_soon_threadsafe(self.did_close.publish, order.id)
                    if order.type == OrderType.liquidation:
                        main_loop.call_soon_threadsafe(self.did_force_liquidate.publish, order)
            except Exception as e:
                logger.error(e)
                continue

    async def close(self) -> Any:
        if self.__exchange:
            await self.__exchange.close()
