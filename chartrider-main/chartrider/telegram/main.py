import logging
import time
from datetime import timedelta

from loguru import logger

from chartrider.settings import LOG_PATH
from chartrider.settings import telegram_settings as settings
from chartrider.telegram.app import create_app
from chartrider.utils.log import InterceptHandler


def main() -> None:
    app = create_app()

    if settings.debug:
        logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    logger.add(LOG_PATH / "telegram-{time}.log", retention=timedelta(days=7))
    logger.info("Waiting for 5 seconds for RabbitMQ...")
    time.sleep(5)
    logger.info("Starting the bot...")
    app.run_polling(
        close_loop=False,
        drop_pending_updates=True,
        timeout=60,
        bootstrap_retries=5,
    )


if __name__ == "__main__":
    main()
