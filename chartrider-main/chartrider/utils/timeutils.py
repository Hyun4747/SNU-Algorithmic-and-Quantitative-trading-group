from datetime import datetime
from typing import TYPE_CHECKING, TypeAlias

import pytz
from ccxt import Exchange

if TYPE_CHECKING:
    from chartrider.core.common.repository.models import Timeframe

Timestamp: TypeAlias = int  # unit: ms
TimeDuration: TypeAlias = int  # unit: ms


class TimeUtils:
    @staticmethod
    def timestamp_in_ms(dt: datetime | None = None) -> Timestamp:
        if dt is None:
            dt = datetime.now(pytz.utc)
        return int(dt.timestamp() * 1000)

    @staticmethod
    def timestamp_to_datetime(
        timestamp: Timestamp, truncate_to_minutes: bool = False, local_timezone: bool = True
    ) -> datetime:
        timestamp = TimeUtils.convert_to_ms_if_needed(timestamp)

        if local_timezone:
            tz = pytz.timezone("Asia/Seoul")
        else:
            tz = pytz.utc

        ret = datetime.fromtimestamp(timestamp / 1000, tz=tz)
        if truncate_to_minutes:
            return ret.replace(second=0, microsecond=0)
        return ret

    @staticmethod
    def timestamp_to_datestring(
        timestamp: Timestamp,
        isoformat: bool = False,
        compact: bool = False,
    ) -> str:
        date = TimeUtils.timestamp_to_datetime(timestamp)
        if isoformat:
            return date.isoformat()
        if compact:
            return date.strftime("%Y.%m.%d %H:%M")
        return date.strftime("%Y-%m-%d %H:%M:%S %z")

    @staticmethod
    def timeframe_in_ms(timeframe: str) -> TimeDuration:
        return Exchange.parse_timeframe(timeframe) * 1000

    @staticmethod
    def round_down_to_timeframe(timestamp: Timestamp, timeframe: "Timeframe") -> Timestamp:
        """Returns the timestamp that is rounded down to the nearest multiple of each timeframe."""
        return timestamp - (timestamp % timeframe.milliseconds)

    @staticmethod
    def round_to_nearest_timeframe_in_minutes(timestamp: Timestamp, timeframe_in_min: int) -> Timestamp:
        timeframe_ms = timeframe_in_min * 60_000
        remainder = timestamp % timeframe_ms
        half_timeframe_ms = timeframe_ms // 2

        if remainder >= half_timeframe_ms:
            return timestamp + (timeframe_ms - remainder)
        else:
            return timestamp - remainder

    @staticmethod
    def convert_to_ms_if_needed(timestamp: int) -> Timestamp:
        # Check if timestamp is in seconds
        if timestamp < 10**12:
            timestamp = timestamp * 1000
        return timestamp
