from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

from chartrider.core.live.io.message import MessageBroker, MessageItem, QueueType
from chartrider.telegram.context import get_user_context
from chartrider.telegram.utils import Emoji


async def user_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assert update.message is not None
    assert (text := update.message.text) is not None
    user_context = get_user_context(context)

    if user_context.input_pending_broker_name is None:
        await update.message.reply_text(f"{Emoji.conversation} I don't understand what you mean.")
        return

    async with MessageBroker(user_context.input_pending_broker_name) as broker:
        await broker.publish(
            QueueType.trader,
            MessageItem(
                body=text,
            ),
        )

    user_context.set_input_pending_broker_name(None)
    user_context.save(context)


input_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, user_input_handler)
