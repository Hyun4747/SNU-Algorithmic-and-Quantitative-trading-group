from enum import Enum, auto
from typing import TypeAlias

from telegram import Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from chartrider.telegram.context import get_user_context
from chartrider.telegram.utils import fallback_func


class State(Enum):
    api_key = auto()
    secret_key = auto()


NextState: TypeAlias = State | int


async def register(update: Update, context: ContextTypes.DEFAULT_TYPE) -> NextState:
    assert update.message is not None

    user_context = get_user_context(context)
    if user_context.testnet is None:
        await update.message.reply_text(
            "Please switch to a valid environment first. Use /switch to switch to a valid environment."
        )
        return ConversationHandler.END

    await update.message.reply_text(f"Please send me your API key for {user_context.environment}.")

    return State.api_key


async def api_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> NextState:
    assert update.message is not None
    api_key = update.message.text

    user_context = get_user_context(context)
    user_context.temp_api_key = api_key
    user_context.save(context)

    await update.message.reply_text(f"Please send me your secret key for {user_context.environment}.")
    return State.secret_key


async def secret_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> NextState:
    assert update.message is not None
    assert (secret_key := update.message.text) is not None

    user_context = get_user_context(context)
    user_context.temp_secret_key = secret_key

    secret = user_context.save_secret_from_input(context)
    if secret is None:
        await update.message.reply_text("Sorry, I could not save your secret key. Please try again.")
        return ConversationHandler.END

    await update.message.reply_text(
        "Thank you! You can now use /run to start trading.",
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> NextState:
    assert update.message is not None
    await update.message.reply_text(
        "You canceled the registration. You can use /register to try again.",
    )
    get_user_context(context).clear(context)
    return ConversationHandler.END


register_secret_handler = ConversationHandler(
    entry_points=[CommandHandler("register", register)],  # type: ignore
    states={
        State.api_key: [MessageHandler(filters.TEXT & ~filters.COMMAND, api_key)],
        State.secret_key: [MessageHandler(filters.TEXT & ~filters.COMMAND, secret_key)],
    },  # type: ignore
    fallbacks=[
        CommandHandler("cancel", cancel),
        MessageHandler(
            filters.TEXT,
            fallback_func("register"),
        ),
    ],  # type: ignore
    allow_reentry=True,
)
