import asyncio
import os
import signal
from datetime import timedelta

from loguru import logger

from chartrider.settings import LOG_PATH
from chartrider.worker.rpc import RpcWorkerServer


async def attach_signal_handlers():
    """Attach signal handlers to the event loop."""
    logger.info("Attaching signal handlers...")
    loop = asyncio.get_event_loop()
    signals = (signal.SIGABRT, signal.SIGTERM, signal.SIGINT)
    for s in signals:
        loop.add_signal_handler(s, lambda s=s: asyncio.create_task(shutdown(s)))


async def shutdown(signal):
    """Cleanup tasks tied to the service's shutdown."""
    logger.info(f"Received exit signal {signal.name}. Cancelling all tasks...")
    for task in asyncio.all_tasks():
        task.cancel()


async def main():
    logger.add(LOG_PATH / "worker-{time}.log", retention=timedelta(days=7))

    await attach_signal_handlers()

    logger.info(f"Starting RPC server as pid {os.getpid()}...")
    async with RpcWorkerServer() as rpc_server:
        try:
            await rpc_server.run()
        except asyncio.CancelledError:
            logger.info("Shutting down RPC server...")
            return


if __name__ == "__main__":
    asyncio.run(main())
