from chartrider.core.common.utils.prompt import prompt_radio
from chartrider.core.strategy.presets import StrategyPreset


def prompt_live_strategies(choices: list[StrategyPreset]) -> StrategyPreset:
    answer = prompt_radio(choices, "Choose the strategy preset for live trading")
    if answer is None:
        raise ValueError("No strategy selected")
    return answer


def prompt_testnet() -> bool:
    testnet = "Testnet"
    mainnet = "Mainnet"
    answer = prompt_radio([testnet, mainnet], "Choose the network for live trading")
    if answer is None:
        raise ValueError("No network selected")
    return answer == testnet
