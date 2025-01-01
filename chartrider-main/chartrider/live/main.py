import asyncio

from chartrider.core.live.execution.builder import build_handler_from_preset
from chartrider.core.live.execution.prompt import prompt_live_strategies, prompt_testnet
from chartrider.utils.secrets import SecretStore

if __name__ == "__main__":
    from chartrider.strategies import strategy_presets

    __testnet = prompt_testnet()
    __strategy_preset = prompt_live_strategies(strategy_presets)
    __secret_store = SecretStore(from_telegram=False)
    __execution_handler = build_handler_from_preset(
        strategy_preset=__strategy_preset,
        secret_store=__secret_store,
        testnet=__testnet,
        use_message_queue=False,
    )
    asyncio.run(__execution_handler.run())
