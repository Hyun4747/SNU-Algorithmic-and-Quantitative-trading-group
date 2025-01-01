import numpy as np
from pydantic import BaseModel, ConfigDict

from chartrider.indicators.ta import TA


class SupertrendResult(BaseModel):
    upper_band: np.ndarray
    lower_band: np.ndarray
    trend: np.ndarray

    model_config: ConfigDict = ConfigDict(arbitrary_types_allowed=True)


def supertrend(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    period: int = 10,
    atr_multiplier: float = 3.0,
    reference: np.ndarray | None = None,
) -> SupertrendResult:
    """
    Example:
    ```python
    def calculate_supertrend(self) -> tuple[SymbolColumnData, SymbolColumnData, SymbolColumnData]:
        up_df = pd.DataFrame(index=self.candle_data.index)
        down_df = pd.DataFrame(index=self.candle_data.index)
        trend_df = pd.DataFrame(index=self.candle_data.index)
        for symbol in self.symbols:
            high = self.candle_data.high[symbol]
            low = self.candle_data.low[symbol]
            close = self.candle_data.close[symbol]
            result = supertrend(
                high.as_array(),
                low.as_array(),
                close.as_array(),
                period=10 * N_CANDLES_PER_DAY,
                atr_multiplier=40,
            )
            up_df[symbol] = result.upper_band
            down_df[symbol] = result.lower_band
            trend_df[symbol] = result.trend
        return (
            SymbolColumnData.from_dataframe(up_df),
            SymbolColumnData.from_dataframe(down_df),
            SymbolColumnData.from_dataframe(trend_df),
        )
    ```
    """

    if reference is None:
        reference = (high + low) / 2

    atr = TA.ATR(high, low, close, timeperiod=period)

    upper_band = reference - (atr_multiplier * atr)
    upper_band_list = [upper_band[0]]
    num_upper_band_crosses = 0

    lower_band = reference + (atr_multiplier * atr)
    lower_band_list = [lower_band[0]]
    num_lower_band_crosses = 0

    trend = 1
    trend_list = [trend]

    for i in range(1, len(high)):
        if trend == 1:
            if close[i] > max(upper_band[num_upper_band_crosses:i]):
                upper_band_list.append(max(upper_band[num_upper_band_crosses:i]))
                lower_band_list.append(np.nan)
            else:
                trend = -1
                num_lower_band_crosses = i
                upper_band_list.append(np.nan)
                lower_band_list.append(lower_band[i])
        else:
            if close[i] < min(lower_band[num_lower_band_crosses:i]):
                upper_band_list.append(np.nan)
                lower_band_list.append(min(lower_band[num_lower_band_crosses:i]))
            else:
                trend = 1
                num_upper_band_crosses = i
                upper_band_list.append(upper_band[i])
                lower_band_list.append(np.nan)
        trend_list.append(trend)

    return SupertrendResult(
        upper_band=np.array(upper_band_list),
        lower_band=np.array(lower_band_list),
        trend=np.array(trend_list),
    )
