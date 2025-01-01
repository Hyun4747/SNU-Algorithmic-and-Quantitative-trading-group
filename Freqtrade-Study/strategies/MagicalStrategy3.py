# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401

# --- Do not remove these libs ---
import numpy as np  # noqa
import pandas as pd  # noqa
from pandas import DataFrame  # noqa
from datetime import datetime, timedelta  # noqa
from typing import Optional, Union  # noqa

from freqtrade.persistence import Order, Trade
from freqtrade.strategy import (BooleanParameter, CategoricalParameter, DecimalParameter,
                                IStrategy, IntParameter)

# --------------------------------
# Add your lib to import here
import talib.abstract as ta
import pandas_ta as pta
import freqtrade.vendor.qtpylib.indicators as qtpylib

# from user_data.strategies.utils import crossed_above_each_hour, crossed_below_each_hour


class MagicalStrategy3(IStrategy):
    """
    This is a strategy template to get you started.
    More information in https://www.freqtrade.io/en/latest/strategy-customization/

    You can:
        :return: a Dataframe with all mandatory indicators for the strategies
    - Rename the class name (Do not forget to update class_name)
    - Add any methods you want to build your strategy
    - Add any lib you need to build your strategy

    You must keep:
    - the lib in the section "Do not remove these libs"
    - the methods: populate_indicators, populate_entry_trend, populate_exit_trend
    You should keep:
    - timeframe, minimal_roi, stoploss, trailing_*
    """

    ########## Configurable params ##########  # TODO: move these into config.json
    # Target volatility
    target_volatility = 0.05

    # Optimal stoploss designed for the strategy.
    # This attribute will be overridden if the config file contains "stoploss".
    stoploss = -0.02

    # timeframe for the strategy.
    timeframe_num = 1
    timeframe_unit = "h"
    timeframe = f"{timeframe_num}{timeframe_unit}"

    if timeframe_unit == "h":
        n_candles_per_day = 24 // timeframe_num
    elif timeframe_unit == "m":
        n_candles_per_day = 24 * 60 // timeframe_num
    else:
        n_candles_per_day = 0
    
    # How long (in minutes or seconds) the bot will wait for an unfilled order
    unfilledtimeout = {
        "entry": 60,
        "exit": 60,
        "exit_timeout_count": 0,
        "unit": "minutes"
    }
    #########################################

    ###### Do not change values below ######
    ########################################
    # Strategy interface version - allow new iterations of the strategy interface.
    # Check the documentation or the Sample strategy to get the latest version.
    INTERFACE_VERSION = 3
    
    # Can this strategy go short?
    can_short: bool = False

    # Minimal ROI designed for the strategy.
    # This attribute will be overridden if the config file contains "minimal_roi".
    minimal_roi = {"0": 10.0}

    # Trailing stoploss
    trailing_stop = False
    # trailing_only_offset_is_reached = False
    # trailing_stop_positive = 0.01
    # trailing_stop_positive_offset = 0.0  # Disabled / not configured

    # To allow partial sell
    position_adjustment_enable = True

    # Run "populate_indicators()" only for new candle.
    process_only_new_candles = False

    # These values can be overridden in the config.
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # Number of candles the strategy requires before producing valid signals
    startup_candle_count: int = 100

    # Strategy parameters
    # buy_rsi = IntParameter(10, 40, default=30, space="buy")
    # sell_rsi = IntParameter(60, 90, default=70, space="sell")

    # Optional order type mapping.
    order_types = {
        'entry': 'limit',
        'exit': 'limit',
        'stoploss': 'market',
        'stoploss_on_exchange': False
    }

    # Optional order time in force.
    order_time_in_force = {
        'entry': 'gtc',
        'exit': 'gtc'
    }
    ########################################
    
    @property
    def plot_config(self):
        return {
            # Main plot indicators (Moving averages, ...)
            'main_plot': {
                'tema': {},
                'sar': {'color': 'white'},
            },
            'subplots': {
                # Subplots - each dict defines one additional plot
                "MACD": {
                    'macd': {'color': 'blue'},
                    'macdsignal': {'color': 'orange'},
                },
                "RSI": {
                    'rsi': {'color': 'red'},
                }
            }
        }

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Adds several different TA indicators to the given DataFrame

        Performance Note: For the best performance be frugal on the number of indicators
        you are using. Let uncomment only the indicator you are using in your strategies
        or your hyperopt configuration, otherwise you will waste your memory and CPU usage.
        :param dataframe: Dataframe with data from the exchange
        :param metadata: Additional information, like the currently traded pair
        :return: a Dataframe with all mandatory indicators for the strategies
        """

        for _tp in [3, 5, 10, 20]:
            dataframe[f"daily_sma{_tp}"] = None
            for _h in range(0, 24, self.timeframe_num):
                each_hour_df = dataframe.loc[dataframe["date"].dt.hour==_h]
                dataframe.loc[dataframe["date"].dt.hour==_h, f"daily_sma{_tp}"] = ta.SMA(each_hour_df[f"close"], timeperiod=_tp)

        dataframe["high_ytd"] = dataframe["high"].rolling(self.n_candles_per_day).max()
        dataframe["low_ytd"] = dataframe["low"].rolling(self.n_candles_per_day).min()
        dataframe["volatility_ytd"] = (dataframe["high_ytd"] - dataframe["low_ytd"]) / dataframe["close"]

        dataframe["volatility"] = None  # SMA(5) of volatility_ytd
        for _h in range(0, 24, self.timeframe_num):
            each_hour_df = dataframe.loc[dataframe["date"].dt.hour==_h]
            dataframe.loc[dataframe["date"].dt.hour==_h, "volatility"] = ta.SMA(each_hour_df["volatility_ytd"], timeperiod=5)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the entry signal for the given dataframe
        :param dataframe: DataFrame
        :param metadata: Additional information, like the currently traded pair
        :return: DataFrame with entry columns populated
        """
        # dataframe.loc[
        #     (
        #         (dataframe["close"] > dataframe["daily_sma3"])
        #         &
        #         (dataframe["close"] > dataframe["daily_sma5"])
        #         &
        #         (dataframe["close"] > dataframe["daily_sma10"])
        #         &
        #         (dataframe["close"] > dataframe["daily_sma20"])
        #     )
        #     &
        #     (
        #         (crossed_above_each_hour(dataframe["close"], dataframe["daily_sma3"]))
        #         |
        #         (crossed_above_each_hour(dataframe["close"], dataframe["daily_sma5"]))
        #         |
        #         (crossed_above_each_hour(dataframe["close"], dataframe["daily_sma10"]))
        #         |
        #         (crossed_above_each_hour(dataframe["close"], dataframe["daily_sma20"]))
        #     )
        #     &
        #     (dataframe["volume"] > 0),
        #     "enter_long"
        # ] = 1

        for _h in range(0, 24, self.timeframe_num):
            each_hour_df = dataframe.loc[dataframe["date"].dt.hour==_h]
            enter_series = (
                (
                    (each_hour_df["close"] > each_hour_df["daily_sma3"])
                    &
                    (each_hour_df["close"] > each_hour_df["daily_sma5"])
                    &
                    (each_hour_df["close"] > each_hour_df["daily_sma10"])
                    &
                    (each_hour_df["close"] > each_hour_df["daily_sma20"])
                )
                &
                (
                    (qtpylib.crossed_above(each_hour_df["close"], each_hour_df["daily_sma3"]))
                    |
                    (qtpylib.crossed_above(each_hour_df["close"], each_hour_df["daily_sma5"]))
                    |
                    (qtpylib.crossed_above(each_hour_df["close"], each_hour_df["daily_sma10"]))
                    |
                    (qtpylib.crossed_above(each_hour_df["close"], each_hour_df["daily_sma20"]))
                )
                &
                (each_hour_df["volume"] > 0)
            )
            enter_index = enter_series[enter_series].index

            dataframe.loc[enter_index, "enter_long"] = 1
        
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the exit signal for the given dataframe
        :param dataframe: DataFrame
        :param metadata: Additional information, like the currently traded pair
        :return: DataFrame with exit columns populated
        """
        # Do nothing as we use custom_exit()!!
        return dataframe

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime, current_rate: float, current_profit: float, **kwargs) -> Optional[Union[str, bool]]:
        dataframe, _ = self.dp.get_analyzed_dataframe(trade.pair, self.timeframe)
        timeframe_delta = timedelta(
            hours=(self.timeframe_num if self.timeframe_unit == "h" else 0),
            minutes=(self.timeframe_num if self.timeframe_unit == "m" else 0),
        )
        order_time = trade.open_date - timeframe_delta
        if current_time.hour == order_time.hour: # trade.open_date.hour: # order_time.hour:
            each_hour_df = dataframe.loc[dataframe["date"].dt.hour==(order_time - timeframe_delta).hour]
            exit_signal = (
                (
                    # (qtpylib.crossed_below(each_hour_df["close"], each_hour_df["daily_sma3"]))
                    # |
                    (qtpylib.crossed_below(each_hour_df["close"], each_hour_df["daily_sma5"]))
                    |
                    (qtpylib.crossed_below(each_hour_df["close"], each_hour_df["daily_sma10"]))
                    |
                    (qtpylib.crossed_below(each_hour_df["close"], each_hour_df["daily_sma20"]))
                )
                &
                (each_hour_df["volume"] > 0)
            ).iloc[-1]
            if exit_signal:
                return "custom_exit"

        return None
    
    def custom_stake_amount(self, pair: str, current_time: datetime, current_rate: float, proposed_stake: float, min_stake: Optional[float], max_stake: float, leverage: float, entry_tag: Optional[str], side: str, **kwargs) -> float:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair=pair, timeframe=self.timeframe)
        current_candle = dataframe.iloc[-1].squeeze()

        proposed_stake = (
            (self.target_volatility / current_candle["volatility"])
            / len(self.config["exchange"]["pair_whitelist"])
            / 24
            * max_stake
        )
        return proposed_stake
