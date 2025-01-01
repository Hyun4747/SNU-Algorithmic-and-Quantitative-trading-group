import asyncio

import click
from loguru import logger
from tqdm import tqdm

from chartrider.core.common.execution.base import BaseExecutionHandler
from chartrider.core.live.broker import LiveBroker
from chartrider.core.strategy.presets import StrategyPreset
from chartrider.utils.exceptions import TerminationSignalReceived
from chartrider.utils.log import sanitize_html


class LiveExecutionHandler(BaseExecutionHandler):
    def __init__(
        self,
        broker: LiveBroker,
        strategy_preset: StrategyPreset,
    ) -> None:
        super().__init__(
            broker=broker,
            strategy_preset=strategy_preset,
        )
        self.broker = broker

    async def setup_logger(self) -> None:
        logger.remove()
        logger.add(sink=lambda msg: tqdm.write(sanitize_html(msg), end=""), colorize=True)
        await self.broker.attach_message_broker()

    async def run(self) -> None:
        try:
            await self.setup_logger()

            logger.info("Setting the margin mode to isolated.")
            self.broker.set_isolated_margin_mode()

            # clean up any existing positions
            await self.broker.cleanup_on_restart()

            # start listening to OHLCV streams
            self.broker.attach_candle_streams()

            # prepare OHLCV data for each symbol
            self.broker.prepare_initial_data()

            logger.info("Setting up strategies.")
            for strategy in self.strategies:
                strategy.setup()

            logger.info("Running the main run loop.\n")

            with tqdm() as pbar:
                pbar.set_description(click.style("[Running]", fg="green", bold=True))
                while True:
                    pbar.set_postfix({"candles": str(self.broker.data_length)})
                    pbar.update(1)

                    try:
                        self.broker.update_latest_ohlcv()
                    except Exception as e:
                        logger.exception(f"Error updating latest OHLCV: {e}")

                    for strategy in self.strategies:
                        strategy.update_indicators()

                    for strategy in self.strategies:
                        # skip strategy if not enough data
                        if self.broker.data_length < strategy.estimated_candles_needed:
                            logger.warning(
                                f"Not enough data ({self.broker.data_length} < {strategy.estimated_candles_needed})!"
                            )
                            continue
                        strategy.next()

                    await logger.complete()  # flush all logs to the sink
                    await self.broker.handle_message()
                    await asyncio.sleep(0.1)
        except (KeyboardInterrupt, asyncio.CancelledError, TerminationSignalReceived):
            logger.info("Termination signal received. Shutting down.")
        except BaseException as e:
            logger.exception(e)
        finally:
            await logger.complete()
            await self.broker.close()
