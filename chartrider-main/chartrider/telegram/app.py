import os

from loguru import logger
from telegram.ext import Application, PicklePersistence

from chartrider.settings import DB_PATH
from chartrider.settings import telegram_settings as settings
from chartrider.telegram import handlers
from chartrider.telegram.context import TelegramUserContext
from chartrider.telegram.utils import (
    Emoji,
    TaskHandler,
    start_handling_incoming_message,
)
from chartrider.worker.rpc import RpcWorkerClient


async def restart_user(user_id: int, app: Application, user_context: TelegramUserContext):
    if app.job_queue is None:
        logger.warning("Job queue is not initialized.")
        return
    async with RpcWorkerClient() as rpc:
        for testnet, container_id in list(user_context.container_ids.items()):
            if not (await rpc.container_exists(container_id)):
                await app.bot.send_message(
                    user_id,
                    (
                        f"{Emoji.announce} It looks like the container {container_id[:7]} is dead now (testnet:"
                        f" {testnet})."
                    ),
                )
                user_context.container_ids.pop(testnet)
            else:
                await start_handling_incoming_message(app.job_queue, user_id, testnet, container_id)
                logger.debug(f"Restarted message broker for {user_id=} {container_id=} (testnet: {testnet}).")
        try:
            app.user_data[user_id]["context"] = user_context
        except KeyError:
            logger.debug(f"User {user_id} has no context. {app.user_data=}")
            pass


async def register_command_handlers(app: Application) -> None:
    await app.bot.set_my_commands(handlers.bot_commands)


async def post_init(app: Application) -> None:
    await register_command_handlers(app)
    for user_id, user_data in app.user_data.items():
        if (user_context := user_data.get("context")) is None or not TelegramUserContext.is_compatible(user_context):
            continue
        await app.bot.send_message(user_id, f"{Emoji.announce} The bot has been restarted (pid: {os.getpid()}).")
        await restart_user(user_id, app, user_context)
    logger.info("The bot has been started.")


async def post_stop(app: Application) -> None:
    await TaskHandler().cancel_tasks()
    for user_id in app.user_data.keys():
        await app.bot.send_message(user_id, f"{Emoji.announce} The bot has been stopped for maintenance.")
    logger.info("The bot has been stopped.")


def create_app() -> Application:
    app = (
        Application.builder()
        .token(settings.token)
        .persistence(PicklePersistence(filepath=DB_PATH / "telegram.db", update_interval=5))
        .read_timeout(60)
        .write_timeout(60)
        .connect_timeout(60)
        .pool_timeout(60)
        .post_init(post_init)
        .post_stop(post_stop)
        .build()
    )
    for command_handler in handlers.command_handlers:
        app.add_handler(command_handler)
    app.add_handler(handlers.register_secret_handler)
    app.add_handler(handlers.run_handler)
    app.add_handler(handlers.env_handler)
    app.add_handler(handlers.input_handler)  # this should go last
    app.add_error_handler(handlers.error_handler)  # type: ignore

    return app
