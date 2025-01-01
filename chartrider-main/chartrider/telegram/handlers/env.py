from enum import Enum, auto
from typing import TypeAlias

from telegram import ReplyKeyboardMarkup, Update
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
    save_environment = auto()


NextState: TypeAlias = State | int


async def switch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> NextState:
    assert update.message is not None

    await update.message.reply_text(
        "Which environment would you like to switch to?",
        reply_markup=ReplyKeyboardMarkup([["testnet"], ["mainnet"]], one_time_keyboard=True),
    )
    return State.save_environment


async def save_environment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> NextState:
    assert update.message is not None
    user_context = get_user_context(context)
    testnet = update.message.text == "testnet"
    user_context.testnet = testnet
    user_context.save(context)

    await update.message.reply_text(f"You have switched to {'testnet' if testnet else 'mainnet'}.")
    return ConversationHandler.END


env_handler = ConversationHandler(
    entry_points=[CommandHandler("switch", switch)],  # type: ignore
    states={
        State.save_environment: [MessageHandler(filters.Regex("^(testnet|mainnet)$"), save_environment)],  # type: ignore
    },
    fallbacks=[
        MessageHandler(
            filters.TEXT,
            fallback_func("switch"),
        )
    ],  # type: ignore
    allow_reentry=True,
)
