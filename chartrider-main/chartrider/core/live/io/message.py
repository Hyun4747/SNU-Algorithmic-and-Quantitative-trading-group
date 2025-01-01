from __future__ import annotations

import asyncio
import enum
import pickle
from typing import Awaitable, Callable

import click
from aio_pika import Message, connect_robust
from aio_pika.abc import (
    AbstractChannel,
    AbstractExchange,
    AbstractIncomingMessage,
    AbstractQueue,
    AbstractRobustConnection,
)
from aio_pika.exceptions import AMQPConnectionError
from loguru import logger
from pydantic import BaseModel

from chartrider.settings import rabbitmq_settings as settings
from chartrider.utils.log import sanitize_html


class MessageBroker:
    def __init__(self, name: str) -> None:
        self.name = name
        self.__connection: AbstractRobustConnection | None = None
        self.__channel: AbstractChannel | None = None
        self.__exchange: AbstractExchange | None = None
        self.__queues: dict[QueueType, AbstractQueue] = dict()

    async def __connect_if_needed(self):
        if self.__connection is not None:
            return
        self.__connection = await connect_robust(settings.url)
        self.__channel = await self.__connection.channel()
        self.__exchange = await self.__channel.declare_exchange(self.name, auto_delete=True)

    async def __declare_queue_if_needed(self, queue_type: QueueType) -> AbstractQueue:
        await self.__connect_if_needed()
        assert self.__channel is not None and self.__exchange is not None
        if queue_type not in self.__queues:
            queue_name = queue_type.get_name(self.name)
            queue = await self.__channel.declare_queue(
                queue_name,
                durable=queue_type.is_durable,
                exclusive=queue_type.is_exclusive,
            )
            await queue.bind(
                self.__exchange,
                routing_key=queue_name,
            )
            self.__queues[queue_type] = queue
        return self.__queues[queue_type]

    async def publish(self, queue_type: QueueType, message: MessageItem) -> None:
        await self.__connect_if_needed()
        assert self.__channel is not None and self.__exchange is not None
        message_bytes = pickle.dumps(message)
        pika_message = Message(body=message_bytes)
        await self.__exchange.publish(pika_message, routing_key=queue_type.get_name(self.name))

    async def consume_and_wait(self, queue_type: QueueType, callback: Callable[[MessageItem], Awaitable[None]]):
        queue = await self.__declare_queue_if_needed(queue_type)

        async def callback_wrapper(message: AbstractIncomingMessage):
            async with message.process():
                assert isinstance(message_item := pickle.loads(message.body), MessageItem)
                await callback(message_item)

        await queue.consume(callback=callback_wrapper)  # register callback
        await asyncio.Future()  # wait forever

    async def consume_one(self, queue_type: QueueType) -> MessageItem | None:
        queue = await self.__declare_queue_if_needed(queue_type)
        incoming_message: AbstractIncomingMessage | None = await queue.get(timeout=30, fail=False)
        if incoming_message is None:
            return None
        async with incoming_message.process():
            assert isinstance(message_item := pickle.loads(incoming_message.body), MessageItem)
            return message_item

    async def consume_and_wait_one(self, queue_type: QueueType) -> MessageItem:
        queue = await self.__declare_queue_if_needed(queue_type)

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process():
                    assert isinstance(message_item := pickle.loads(message.body), MessageItem)
                    return message_item

        raise AssertionError("No message found")

    async def close(self):
        if self.__connection is None:
            return
        await self.__connection.close()
        self.__connection = None
        self.__channel = None
        self.__exchange = None
        self.__queues = dict()

    async def __aenter__(self):
        await self.__connect_if_needed()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.close()


class QueueType(enum.Enum):
    telegram = enum.auto()
    trader = enum.auto()

    @property
    def is_exclusive(self) -> bool:
        """
        The trader queue that stores message from the telegram should be used by only one connection,
        and should be deleted when that connection closes.
        """
        return self == QueueType.trader

    @property
    def is_durable(self) -> bool:
        """
        The telegram queue that stores message from the live trader should survive a broker restart.
        """
        return self == QueueType.telegram

    def get_name(self, exchange_name: str) -> str:
        return f"{exchange_name}-{self.name}"


class CommandType(enum.Enum):
    stop = enum.auto()
    status = enum.auto()

    @property
    def description(self) -> str:
        return {
            CommandType.stop: "Stop the bot.",
            CommandType.status: "Show the bot status.",
        }[self]


class MessageItem(BaseModel):
    body: str | None = None
    command: CommandType | None = None

    reply_options: list[str] | None = None


async def connect_to_rabbitmq(url: str) -> AbstractRobustConnection:
    while True:
        try:
            connection = await connect_robust(url)
        except AMQPConnectionError:
            logger.warning("Failed to connect to RabbitMQ. Retrying...")
            await asyncio.sleep(1)
        else:
            logger.info("Successfully connected to RabbitMQ.")
            return connection


async def route_logger_to_queue(message_queue: MessageBroker):
    async def sink(message: str):
        await message_queue.publish(
            QueueType.telegram,
            MessageItem(
                body=click.unstyle(message),
            ),
        )

    # Ensure all sink coroutines are running in the main event loop
    # in case the logger is called in a different event loop.
    main_event_loop = asyncio.get_event_loop()
    logger.add(sink, format="[{level}] {message}", level="INFO", loop=main_event_loop)


async def echo(message_queue: MessageBroker | None, text: str):
    if message_queue is None:
        click.echo(sanitize_html(text))
        return

    await message_queue.publish(
        QueueType.telegram,
        MessageItem(
            body=text,
        ),
    )


async def confirm(message_queue: MessageBroker | None, text: str) -> bool:
    if message_queue is None:
        return click.confirm(text)

    while True:
        ask_message = MessageItem(
            body=text,
            reply_options=["Yes", "No"],
        )
        await message_queue.publish(QueueType.telegram, ask_message)

        reply_message = await message_queue.consume_and_wait_one(QueueType.trader)
        if ask_message.reply_options and reply_message.body not in ask_message.reply_options:
            await echo(message_queue, "Please select a valid option.")
            continue

        return reply_message.body == "Yes"
