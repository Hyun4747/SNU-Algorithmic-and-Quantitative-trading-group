from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from chartrider.database.base import DeclarativeBase, intpk, str20, str50


class ContingentInfo(DeclarativeBase):
    __tablename__ = "contingent_info"
    __table_args__ = (
        UniqueConstraint("user_id", "order_id", "symbol", "testnet", name="unique_user_order_symbol_testnet"),
    )

    id: Mapped[intpk]
    user_id: Mapped[str50]
    order_id: Mapped[str50]
    side: Mapped[str20]
    symbol: Mapped[str20]
    testnet: Mapped[bool] = mapped_column(default=False)
    sl_trigger_price: Mapped[float | None]
    sl_execute_price: Mapped[float | None]
    tp_trigger_price: Mapped[float | None]
    tp_execute_price: Mapped[float | None]

    is_triggered: Mapped[bool] = mapped_column(default=False)
