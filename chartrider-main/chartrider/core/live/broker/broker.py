import click
from loguru import logger

from chartrider.core.common.broker.base import BaseBroker
from chartrider.core.common.repository.eventmonitor.monitor import EventMonitor
from chartrider.core.common.repository.models import Order, Timeframe
from chartrider.core.live.io.message import (
    CommandType,
    MessageBroker,
    QueueType,
    confirm,
    echo,
    route_logger_to_queue,
)
from chartrider.core.live.repository import LiveRepository
from chartrider.utils.exceptions import TerminationSignalReceived
from chartrider.utils.timeutils import TimeUtils


class LiveBroker(BaseBroker):
    def __init__(
        self, repository: LiveRepository, event_monitor: EventMonitor, message_broker: MessageBroker | None = None
    ) -> None:
        super().__init__(repository, event_monitor)
        self.repository = repository
        self.message_broker = message_broker

    async def attach_message_broker(self) -> None:
        if self.message_broker is None:
            return
        await route_logger_to_queue(self.message_broker)

    def prepare_initial_data(self) -> None:
        assert self._registered_strategies, "No strategies registered"
        prepended_duration = self.max_candles_needed * Timeframe.m1.milliseconds
        symbols = list(self.symbols)
        if len(symbols) > 1:
            self.repository.fetch_ohlcv_bulk(
                symbols=symbols,
                timeframe=Timeframe.m1,
                since=TimeUtils.timestamp_in_ms() - prepended_duration,
                until=None,
            )
        else:
            self.repository.fetch_ohlcv(
                symbol=symbols[0],
                timeframe=Timeframe.m1,
                since=TimeUtils.timestamp_in_ms() - prepended_duration,
                until=None,
            )

    def attach_candle_streams(self) -> None:
        self.repository.watch_events()
        for symbol in self.symbols:
            self.repository.watch_candles(symbol, Timeframe.m1)

    def update_latest_ohlcv(self) -> None:
        for symbol in self.symbols:
            self.repository.update_latest_ohlcv(
                symbol,
                timeframe=Timeframe.m1,
                limit=5,
            )
        self.candle_data.truncate_to(self.max_candles_needed)
        self.repository.next()

    async def cleanup_on_restart(self) -> None:
        # cancel all open orders
        open_orders: list[Order] = []
        for symbol in self.symbols:
            open_orders.extend(self.repository.fetch_open_orders(symbol))

        if open_orders:
            if not self.message_broker:
                click.echo()
                for order in open_orders:
                    await echo(self.message_broker, order.format(html=True))

            if await confirm(
                self.message_broker,
                f"You have {len(open_orders)} open orders. Do you want to cancel them all?",
            ):
                for symbol in self.symbols:
                    self.repository.cancel_all_orders(symbol)

        # liquidate all open positions
        positions = self.repository.fetch_positions(self.symbols)

        if positions:
            for position in positions:
                await echo(self.message_broker, position.format(html=True))

            if await confirm(
                self.message_broker,
                f"You have {len(positions)} open positions. Do you want to close them all?",
            ):
                for position in positions:
                    self.repository.close_position(position)

    async def handle_message(self) -> None:
        if self.message_broker is None:
            return
        message = await self.message_broker.consume_one(QueueType.trader)
        if message is None:
            return

        match message.command:
            case CommandType.stop:
                raise TerminationSignalReceived
            case CommandType.status:
                logger.info("Your trader is working fine.")
                for position in self.repository.fetch_positions(self.symbols):
                    await echo(self.message_broker, position.format(html=True))
            case _:
                logger.warning(f"Unknown command received: {message.command}")

    async def close(self) -> None:
        await self.repository.close()
        if self.message_broker:
            await logger.complete()
            await self.message_broker.close()
        if self.event_monitor:
            await self.event_monitor.close()
