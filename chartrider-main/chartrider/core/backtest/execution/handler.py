import asyncio
from datetime import datetime

from devtools import debug
from loguru import logger
from tqdm import tqdm, trange

from chartrider.core.backtest.broker import BacktestBroker
from chartrider.core.backtest.execution.postprocessor import BacktestPostprocessor
from chartrider.core.common.execution.base import BaseExecutionHandler
from chartrider.core.strategy.presets import StrategyPreset
from chartrider.utils.profiler import profile


class BacktestExecutionHandler(BaseExecutionHandler):
    def __init__(
        self,
        start: datetime,
        end: datetime,
        broker: BacktestBroker,
        strategy_preset: StrategyPreset,
    ) -> None:
        super().__init__(
            broker=broker,
            strategy_preset=strategy_preset,
        )
        self.start = start.astimezone()
        self.end = end.astimezone()
        self.broker = broker

    def postprocess(self) -> None:
        postprocessor = BacktestPostprocessor(execution_handler=self)
        postprocessor.process()

    def setup_logger(self) -> None:
        logger.remove()
        logger.add(sink=lambda msg: tqdm.write(msg, end=""), colorize=True)

    @profile
    def run(self) -> None:
        try:
            self.setup_logger()

            timer = debug.timer(verbose=False).start()

            logger.info("Setting the margin mode to isolated.")
            self.broker.set_isolated_margin_mode()

            logger.info("Preparing data.")
            self.broker.prepare_initial_data(self.start, self.end)

            logger.info("Setting up indicators for strategies.")
            for strategy in self.strategies:
                strategy.setup()
                strategy.update_indicators()

            # cache the original data length
            data_length = self.broker.data_length

            assert (
                self.broker.max_candles_needed_for_indicators <= self.broker.max_candles_needed
            ), "The number of candles required by the indicators is greater than your estimates."

            with trange(self.broker.max_candles_needed + 1, data_length) as pbar:
                pbar.set_description("[Backtest]")
                for i in pbar:
                    self.broker.set_length(i)
                    self.broker.next()

                    if self.broker.repository.fetch_balance().totalMarginBalance <= 0:
                        logger.warning("Margin Balance is zero. Stopping backtest.")
                        break

                    for strategy in self.strategies:
                        strategy.next()
                else:
                    for strategy in self.strategies:
                        strategy.clear_all()

                    self.broker.set_length(data_length)
                    self.broker.next()

            elapsed = round(timer.capture().elapsed(), 2)
            logger.success(f"Backtest finished successfully in {elapsed} seconds.")

            self.postprocess()
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt detected. Stopping backtest.")
            return
        finally:
            asyncio.run(self.broker.close())
