from sqlalchemy import BigInteger, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from chartrider.database.base import DeclarativeBase, intpk, str10, str20


class Dataset(DeclarativeBase):
    __tablename__ = "dataset"
    __table_args__ = (UniqueConstraint("symbol", "timeframe"),)

    id: Mapped[intpk]
    symbol: Mapped[str20]
    timeframe: Mapped[str10]


class Candle(DeclarativeBase):
    __tablename__ = "candle"
    dataset_id: Mapped[int] = mapped_column(ForeignKey("dataset.id", ondelete="CASCADE"), primary_key=True)
    timestamp: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    open: Mapped[float]
    close: Mapped[float]
    high: Mapped[float]
    low: Mapped[float]
    volume: Mapped[float]
