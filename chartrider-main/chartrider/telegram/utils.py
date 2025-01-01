import asyncio
import hashlib
from typing import Any, Coroutine, Iterable

from loguru import logger
from telegram import ReplyKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext, ContextTypes, ConversationHandler, JobQueue

from chartrider.core.live.io.message import MessageBroker, MessageItem, QueueType
from chartrider.telegram.context import get_user_context


class SingletonMeta(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = instance
        return cls._instances[cls]


class TaskHandler(metaclass=SingletonMeta):
    def __init__(self):
        self.tasks = []

    async def add_task(self, task: Coroutine[Any, Any, None]):
        self.tasks.append(asyncio.create_task(task))

    async def cancel_tasks(self):
        for task in self.tasks:
            task.cancel()


def make_keyboard_array(arr: Iterable[str]) -> list[list[str]]:
    column = 2
    str_arr = list(map(str, arr))
    nested_array = []
    for i in range(0, len(str_arr), column):
        nested_array.append(str_arr[i : i + column])
    return nested_array


async def start_handling_incoming_message(job_queue: JobQueue, user_id: int, testnet: bool, container_id: str) -> None:
    job_name = get_job_name(user_id, testnet)
    if job_queue.get_jobs_by_name(job_name):
        # Job already running
        return
    job_queue.run_once(
        handle_incoming_message,
        when=1,
        name=job_name,
        user_id=user_id,
        job_kwargs={"misfire_grace_time": 60},
        data={"container_id": container_id, "testnet": testnet},
    )


async def handle_incoming_message(context: CallbackContext) -> None:
    try:
        assert context.job is not None and isinstance(context.job.data, dict)
        assert (user_id := context.job.user_id) is not None

        container_id = context.job.data.get("container_id")
        testnet = context.job.data.get("testnet")

        if container_id is None or testnet is None:
            raise ValueError("Invalid job data.")

        broker_name = get_user_context(context).get_message_queue_name_by(testnet)
        assert broker_name is not None
        message_broker = MessageBroker(name=broker_name)

        async def callback(message: MessageItem) -> None:
            # no reply
            if message.body and not message.reply_options:
                await context.bot.send_message(
                    user_id,
                    text=f"{Emoji.incoming} {message.body}",
                    parse_mode=ParseMode.HTML,
                )
                return

            # reply
            if message.body and message.reply_options:
                user_context = get_user_context(context)
                await context.bot.send_message(
                    user_id,
                    text=f"{Emoji.incoming_reply} {message.body}",
                    reply_markup=ReplyKeyboardMarkup([message.reply_options], one_time_keyboard=True),
                    parse_mode=ParseMode.HTML,
                )
                user_context.set_input_pending_broker_name(message_broker.name)
                user_context.save(context)
                return

        await context.bot.send_message(
            user_id,
            (
                f"{Emoji.announce} The message broker is now listening to container {container_id[:7]} (testnet:"
                f" {testnet})."
            ),
        )

        # Don't await the infinite task in the job queue.
        await TaskHandler().add_task(message_broker.consume_and_wait(QueueType.telegram, callback))
    except Exception as e:
        logger.exception(e)
        if context.job is not None and (user_id := context.job.user_id) is not None:
            await context.bot.send_message(
                user_id,
                text=f"{Emoji.incoming} {e}",
            )


def get_job_name(user_id: int, testnet: bool) -> str:
    return hashlib.md5(f"handle_incoming_message-{user_id}-{testnet}".encode()).hexdigest()


def fallback_func(command: str):
    async def fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
        assert update.message is not None
        await update.message.reply_text(
            f"Sorry, I did not understand that. Please use /{command} to try again.",
        )
        return ConversationHandler.END

    return fallback


class Emoji:
    incoming = "📨"
    incoming_reply = "📝"
    announce = "📢"
    conversation = "💬"
