from chartrider.core.common.repository.candle.repository import (
    CandleAPIRepository,
    CandleDBRepository,
    CandleRepository,
)
from chartrider.core.common.repository.contingent.repository import (
    ContingentInfoDBRepository,
)
from chartrider.core.common.repository.eventmonitor.monitor import EventMonitor
from chartrider.core.live.broker import LiveBroker
from chartrider.core.live.execution.handler import LiveExecutionHandler
from chartrider.core.live.io.message import MessageBroker
from chartrider.core.live.repository import LiveRepository
from chartrider.core.strategy.presets import StrategyPreset
from chartrider.database.connection import DBSessionFactory
from chartrider.utils.exchange import ExchangeFactory
from chartrider.utils.secrets import SecretStore


def build_handler_from_preset(
    strategy_preset: StrategyPreset,
    secret_store: SecretStore,
    testnet: bool,
    use_message_queue: bool = True,
) -> LiveExecutionHandler:
    assert (secret := secret_store.get_secret(testnet)) is not None
    message_queue = MessageBroker(secret.hash()) if use_message_queue else None
    exchange_factory = ExchangeFactory(secret_store)
    session_factory = DBSessionFactory()
    candle_db_repository = CandleDBRepository(session_factory=session_factory)
    candle_api_repository = CandleAPIRepository(
        exchange=exchange_factory.get_public_exchange(use_testnet=False),
        async_exchange=exchange_factory.get_public_async_exchange(use_testnet=False),
    )
    candle_repository = CandleRepository(db_repository=candle_db_repository, api_repository=candle_api_repository)
    contingent_repository = ContingentInfoDBRepository(
        session_factory=session_factory, testnet=testnet, user_id=secret.hash()
    )
    event_monitor = EventMonitor(exchange=exchange_factory.get_async_exchange(testnet))
    live_repository = LiveRepository(
        exchange=exchange_factory.get_exchange(testnet),
        candle_repository=candle_repository,
        contingent_info_repository=contingent_repository,
        event_monitor=event_monitor,
    )
    broker = LiveBroker(repository=live_repository, event_monitor=event_monitor, message_broker=message_queue)
    return LiveExecutionHandler(broker=broker, strategy_preset=strategy_preset)
