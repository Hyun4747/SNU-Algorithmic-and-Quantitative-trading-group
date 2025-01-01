from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chartrider.core.strategy.presets import StrategyPreset

# from .daily_clv_long import presets as daily_clv_long_presets
# from .daily_rsi_clv_long import presets as daily_rsi_clv_presets
# from .daily_rsi_long import presets as daily_rsi_presets
# from .random_buy import presets as random_buy_presets
from .simple_vb import presets as simple_vb_presets
from .simple_vb_deadcross import presets as simple_vb_deadcross_presets
from .simple_vbdc_cumulative import presets as simple_vbdc_cumulative_presets
from .volatility_breakout import presets as volatility_breakout_presets

strategy_presets: list["StrategyPreset"] = []
# strategy_presets += [*random_buy_presets]
strategy_presets += [*simple_vb_presets]
strategy_presets += [*simple_vb_deadcross_presets]
strategy_presets += [*simple_vbdc_cumulative_presets]
strategy_presets += [*volatility_breakout_presets]
# strategy_presets += [*daily_clv_long_presets]
# strategy_presets += [*daily_rsi_presets]
# strategy_presets += [*daily_rsi_clv_presets]
