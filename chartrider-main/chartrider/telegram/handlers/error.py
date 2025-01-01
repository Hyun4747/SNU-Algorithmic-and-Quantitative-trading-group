import html
import json
import traceback

from loguru import logger
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext


async def error_handler(update: Update | None, context: CallbackContext):
    if update is None:
        logger.exception(context.error)
        return
    assert context.error is not None and update.message is not None
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)

    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    message = (
        "An exception was raised while handling an update.\n\n"
        f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}"
        "</pre>\n\n"
        f"<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>\n\n"
        f"<pre>context.user_data = {html.escape(str(context.user_data))}</pre>\n\n"
        f"<pre>{html.escape(tb_string)}</pre>"
    )

    if len(message) > 8192:
        message = message[:4096] + "..." + message[-4096:]

    await update.message.reply_text(message, parse_mode=ParseMode.HTML)
