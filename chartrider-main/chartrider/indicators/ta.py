import numpy as np
import talib


class TA:
    """
    A wrapper collection of talib indicators.
    It provides a convenient way to access talib indicators and offers auto suggestion.
    """

    @staticmethod
    def ATR(high: np.ndarray, low: np.ndarray, close: np.ndarray, timeperiod=14) -> np.ndarray:
        atr = talib.ATR(high, low, close, timeperiod)  # type: ignore
        return atr
