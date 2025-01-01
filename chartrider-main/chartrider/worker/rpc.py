import asyncio
from typing import Awaitable, Callable

from aio_pika.abc import AbstractChannel, AbstractRobustConnection
from aio_pika.patterns import RPC

from chartrider.core.live.io.message import connect_to_rabbitmq
from chartrider.settings import rabbitmq_settings as settings
from chartrider.telegram.context import TelegramUserContext
from chartrider.worker.procedures import (
    container_exists,
    create_isolated_container,
    kill_container,
)


class RpcWorker:
    def __init__(self) -> None:
        self.__connection: AbstractRobustConnection | None = None
        self.__channel: AbstractChannel | None = None
        self.rpc: RPC | None = None

    async def __aenter__(self):
        self.__connection = await connect_to_rabbitmq(settings.url)
        self.__channel = await self.__connection.channel()
        self.rpc = await RPC.create(self.__channel)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self.__connection is None:
            return
        await self.__connection.close()
        self.__connection = None
        self.__channel = None
        self.rpc = None


class RpcWorkerServer(RpcWorker):
    async def __aenter__(self):
        await super().__aenter__()
        await self.register_all_methods()
        return self

    async def register_all_methods(self) -> None:
        await self.register_method(create_isolated_container)
        await self.register_method(container_exists)
        await self.register_method(kill_container)

    async def register_method(self, method: Callable[..., Awaitable]) -> None:
        assert self.rpc is not None
        await self.rpc.register(method.__name__, method, auto_delete=True)

    async def run(self):
        await asyncio.Future()


class RpcWorkerClient(RpcWorker):
    async def __aenter__(self):
        await super().__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await super().__aexit__(exc_type, exc, tb)

    async def create_isolated_container(self, user_context: TelegramUserContext) -> str:
        assert self.rpc is not None
        return await self.rpc.proxy.create_isolated_container(user_context=user_context)

    async def container_exists(self, container_id: str) -> bool:
        assert self.rpc is not None
        return await self.rpc.proxy.container_exists(container_id=container_id)

    async def kill_container(self, container_id: str) -> bool:
        assert self.rpc is not None
        return await self.rpc.proxy.kill_container(container_id=container_id)
