import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Awaitable, Callable, Coroutine, Self, TypeVar

T = TypeVar("T")


class AsyncEventLoop:
    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.executor: ThreadPoolExecutor | None = None

    def add_task(self, task: Coroutine[Any, Any, None]):
        return asyncio.run_coroutine_threadsafe(task, self.loop)

    def await_task(self, coroutine: Awaitable[T], timeout=None) -> T:
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop).result(timeout)

    def start_loop(self, num_threads=1) -> Self:
        if self.executor is not None:
            raise RuntimeError("Event loop is already running.")

        def loop_runner():
            asyncio.set_event_loop(self.loop)
            self.loop.run_forever()

        self.executor = ThreadPoolExecutor(max_workers=num_threads)
        self.executor.submit(loop_runner)
        return self

    async def perform(self, sync_func: Callable[..., T], *args) -> T:
        return await self.loop.run_in_executor(self.executor, sync_func, *args)

    def stop_loop(self):
        for task in asyncio.all_tasks(loop=self.loop):
            task.cancel()

        self.loop.call_soon_threadsafe(self.loop.stop)

        if self.executor is not None:
            self.executor.shutdown(wait=True)

        self.executor = None
