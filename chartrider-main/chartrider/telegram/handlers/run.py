from enum import Enum, auto
from textwrap import dedent
from typing import TypeAlias

from telegram import ForceReply, ReplyKeyboardMarkup, Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from chartrider.strategies import strategy_presets
from chartrider.telegram.context import get_user_context
from chartrider.telegram.utils import (
    Emoji,
    fallback_func,
    make_keyboard_array,
    start_handling_incoming_message,
)
from chartrider.worker.rpc import RpcWorkerClient


class State(Enum):
    choose_strategy_preset = auto()
    confirm_run = auto()
    enqueue_job = auto()


NextState: TypeAlias = State | int


async def run(update: Update, context: ContextTypes.DEFAULT_TYPE) -> NextState:
    assert update.message is not None
    assert update.effective_user is not None

    user_context = get_user_context(context)
    user_context.username = update.effective_user.username
    user_context.save(context)

    if user_context.username is None:
        await update.message.reply_text(
            "Please set your username first. You can do so by going to Settings > Username in the Telegram app."
        )
        return ConversationHandler.END

    if user_context.testnet is None:
        await update.message.reply_text(
            "Please switch to a valid environment first. Use /switch to switch to a valid environment."
        )
        return ConversationHandler.END

    if user_context.secret_store.get_secret(user_context.testnet) is None:
        await update.message.reply_text("Please set your secret first. Use /register to set your secret.")
        return ConversationHandler.END

    if container_id := user_context.container_id:
        async with RpcWorkerClient() as rpc_client:
            if await rpc_client.container_exists(container_id):
                await update.message.reply_text(
                    "You already have a running container. Please /stop or /kill it first."
                )
                return ConversationHandler.END
            else:
                user_context.set_container_id(None)
                user_context.save(context)

    presets_choices = "".join(
        f"""
    <u>{i}. {preset.name}</u>
    <i>{preset.description}</i>
    """
        for i, preset in enumerate(strategy_presets, 1)
    )

    html_message = f"""
    {Emoji.conversation} Please choose a strategy preset.
    {presets_choices}
    """
    await update.message.reply_html(
        dedent(html_message),
        reply_markup=ReplyKeyboardMarkup(
            make_keyboard_array(str(i) for i in range(1, len(strategy_presets) + 1)), one_time_keyboard=True
        ),
    )

    return State.choose_strategy_preset


async def choose_strategy_preset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> NextState:
    assert update.message is not None
    assert context.user_data is not None

    try:
        chosen_preset_index = int(str(update.message.text)) - 1
        chosen_preset = strategy_presets[chosen_preset_index]
    except (ValueError, IndexError, TypeError, AttributeError):
        await update.message.reply_html(
            r"Invalid preset index. Please choose a valid preset index.",
            reply_markup=ForceReply(selective=True),
        )
        return State.choose_strategy_preset

    user_context = get_user_context(context)
    user_context.strategy_preset = chosen_preset
    user_context.save(context)

    await update.message.reply_html(
        rf"{Emoji.conversation} Please confirm that you want to run the <b>{chosen_preset.name}</b> strategy preset.",
        reply_markup=ReplyKeyboardMarkup([["Yes"], ["No"]], one_time_keyboard=True),
    )

    return State.confirm_run


async def confirm_run(update: Update, context: ContextTypes.DEFAULT_TYPE) -> NextState:
    assert update.message is not None
    assert update.effective_message is not None
    assert update.effective_user is not None
    assert context.job_queue is not None

    confirmed = update.message.text == "Yes"
    if not confirmed:
        await update.message.reply_text(
            r"Cancelled.",
        )
        return ConversationHandler.END

    user_context = get_user_context(context)
    assert user_context.testnet is not None

    async with RpcWorkerClient() as rpc:
        container_id = await rpc.create_isolated_container(user_context)
        user_context.set_container_id(container_id)
        user_context.save(context)

    await start_handling_incoming_message(
        context.job_queue, update.effective_user.id, user_context.testnet, container_id
    )
    await update.message.reply_text(
        f"{Emoji.announce} Your job has been successfully started on a container {container_id[:7]}."
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> NextState:
    assert update.message is not None
    assert context.user_data is not None

    await update.message.reply_text(
        "Please use /run to run a new job.",
    )

    return ConversationHandler.END


run_handler = ConversationHandler(
    entry_points=[CommandHandler("run", run)],  # type: ignore
    states={
        State.choose_strategy_preset: [MessageHandler(filters.Regex(r"^\d+$"), choose_strategy_preset)],
        State.confirm_run: [MessageHandler(filters.Regex("^(Yes|No)$"), confirm_run)],
    },  # type: ignore
    fallbacks=[
        CommandHandler("cancel", cancel),
        MessageHandler(
            filters.TEXT,
            fallback_func("run"),
        ),
    ],  # type: ignore
    allow_reentry=True,
)
