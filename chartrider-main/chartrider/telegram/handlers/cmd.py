from typing import Any, Callable

from loguru import logger
from telegram import BotCommand, Update
from telegram.ext import CommandHandler, ContextTypes

from chartrider.core.live.io.message import (
    CommandType,
    MessageBroker,
    MessageItem,
    QueueType,
)
from chartrider.telegram.context import get_user_context
from chartrider.telegram.utils import Emoji
from chartrider.worker.rpc import RpcWorkerClient


def create_command_handler(command: CommandType):
    async def _command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        assert update.message is not None
        user_context = get_user_context(context)
        logger.debug(
            f"Received command {command.name} from {update.message.from_user}, context.user_data: {context.user_data},"
            f" queue_name: f{user_context.get_message_queue_name()},"
            f" secret_store:{user_context.secret_store.get_secret(True)}."
        )

        queue_name = user_context.get_message_queue_name()
        if queue_name is None:
            await update.message.reply_text("Please make sure you have correctly set up your environment and secrets.")
            return

        async with MessageBroker(queue_name) as broker:
            await broker.publish(
                QueueType.trader,
                MessageItem(command=command),
            )

    return _command_handler


async def force_kill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assert update.message is not None
    user_context = get_user_context(context)

    async with RpcWorkerClient() as rpc:
        if user_context.container_id is not None and await rpc.kill_container(user_context.container_id):
            await update.message.reply_text(f"{Emoji.conversation} Killed container {user_context.container_id[:7]}.")
            return

    await update.message.reply_text(f"{Emoji.conversation} You don't have a running container.")
    user_context.set_container_id(None)
    user_context.save(context)


async def is_container_running(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assert update.message is not None
    user_context = get_user_context(context)

    async with RpcWorkerClient() as rpc:
        if user_context.container_id is None or not await rpc.container_exists(user_context.container_id):
            await update.message.reply_text("You don't have a running container.")
            user_context.set_container_id(None)
            user_context.save(context)
            return

    await update.message.reply_text(
        f"{Emoji.conversation} Your instance is running on container {user_context.container_id[:7]}.\n"
        "If you want to receive status updates, use /status.\n"
        "If you want to stop it, use /stop or /kill."
    )


async def my_context(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assert update.message is not None
    user_context = get_user_context(context)
    await update.message.reply_text(
        f"{Emoji.conversation}\nContext: {user_context}\nSecret(Testnet):"
        f" {user_context.secret_store.get_secret(True)}\nSecret(Live): {user_context.secret_store.get_secret(False)}"
    )


class CommandHandlerWrapper:
    def __init__(self, command: str, description: str, handler: Callable[[Update, ContextTypes.DEFAULT_TYPE], Any]):
        self.command = command
        self.description = description
        self.handler = handler

    @property
    def as_bot_command(self) -> BotCommand:
        return BotCommand(self.command, self.description)

    @property
    def as_cmd_handler(self) -> CommandHandler:
        return CommandHandler(self.command, self.handler)


command_handler_wrappers = [
    CommandHandlerWrapper(command.name, command.description, create_command_handler(command))
    for command in CommandType
]
command_handler_wrappers += [CommandHandlerWrapper("kill", "Forcibly kill current running container.", force_kill)]
command_handler_wrappers += [CommandHandlerWrapper("context", "Show current context.", my_context)]
command_handler_wrappers += [
    CommandHandlerWrapper("is_running", "Check if there's running container.", is_container_running)
]
command_handlers = [handler.as_cmd_handler for handler in command_handler_wrappers]
