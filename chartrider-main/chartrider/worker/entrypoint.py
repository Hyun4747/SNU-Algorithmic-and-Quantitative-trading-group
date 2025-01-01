import asyncio
import pickle
import sys

from loguru import logger

from chartrider.core.live.execution.builder import build_handler_from_preset
from chartrider.settings import LOG_PATH
from chartrider.settings import telegram_settings as settings
from chartrider.telegram.context import TelegramUserContext

if __name__ == "__main__":
    try:
        user_context_bytes = bytes.fromhex(sys.argv[1])
        user_context = pickle.loads(user_context_bytes)
        assert isinstance(user_context, TelegramUserContext)
        assert user_context.strategy_preset is not None
        assert user_context.testnet is not None

        if settings.debug:
            log_prefix = (
                f"{user_context.username or 'NA'}-{user_context.environment}-{user_context.get_message_queue_name()}-"
            )
            logger.add(LOG_PATH / (log_prefix + "{time}.log"))

        live_execution_handler = build_handler_from_preset(
            strategy_preset=user_context.strategy_preset,
            secret_store=user_context.secret_store,
            testnet=user_context.testnet,
        )
        asyncio.run(live_execution_handler.run())
    except Exception as e:
        logger.add(LOG_PATH / "entrypoint-{time}.log")
        logger.exception(e)
        raise
