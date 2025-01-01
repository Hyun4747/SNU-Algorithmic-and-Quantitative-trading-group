from abc import ABC, abstractmethod

from pydantic import BaseModel
from pydantic.config import ConfigDict
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from chartrider.core.common.repository.contingent.schemas import ContingentInfo
from chartrider.core.common.repository.models import ContingentOrder, PositionSide
from chartrider.database.connection import DBSessionFactory
from chartrider.utils.symbols import Symbol


class ContingentInfoDto(BaseModel):
    order_id: str
    user_id: str
    side: PositionSide
    symbol: Symbol
    testnet: bool
    sl_trigger_price: float | None
    sl_execute_price: float | None
    tp_trigger_price: float | None
    tp_execute_price: float | None
    is_triggered: bool = False

    model_config = ConfigDict(from_attributes=True)


class ContingentInfoBaseRepository(ABC):
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id

    @abstractmethod
    def create_contingent_info(
        self,
        order_id: str,
        symbol: Symbol,
        side: PositionSide,
        contingent_sl: ContingentOrder | None = None,
        contingent_tp: ContingentOrder | None = None,
    ) -> None:
        ...

    @abstractmethod
    def get_contingent_info(self, order_id: str, symbol: Symbol) -> ContingentInfoDto | None:
        ...

    @abstractmethod
    def delete_contingent_info(self, order_id: str, symbol: Symbol) -> None:
        ...

    @abstractmethod
    def delete_pending_contingent_infos(self, symbol: Symbol, side: PositionSide) -> None:
        ...

    @abstractmethod
    def get_pending_contingent_infos(self) -> list[ContingentInfoDto]:
        ...

    @abstractmethod
    def mark_contingent_info_as_triggered(self, order_id: str, symbol: Symbol) -> None:
        ...

    @abstractmethod
    def is_liquidated_by_contingent(self, order_id: str, symbol: Symbol) -> bool:
        ...

    @abstractmethod
    def get_all_contingent_infos(self) -> list[ContingentInfoDto]:
        ...


class ContingentInfoInMemoryRepository(ContingentInfoBaseRepository):
    def __init__(self, user_id: str) -> None:
        super().__init__(user_id=user_id)
        self.database: dict[tuple[str, Symbol], ContingentInfoDto] = dict()

    def create_contingent_info(
        self,
        order_id: str,
        symbol: Symbol,
        side: PositionSide,
        contingent_sl: ContingentOrder | None = None,
        contingent_tp: ContingentOrder | None = None,
    ) -> None:
        key = (order_id, symbol)
        if key in self.database:
            raise ValueError("ContingentInfo already exists.")
        self.database[key] = ContingentInfoDto(
            order_id=order_id,
            side=side,
            user_id=self.user_id,
            symbol=symbol,
            testnet=False,
            sl_trigger_price=contingent_sl.triggerPrice if contingent_sl else None,
            sl_execute_price=contingent_sl.price if contingent_sl else None,
            tp_trigger_price=contingent_tp.triggerPrice if contingent_tp else None,
            tp_execute_price=contingent_tp.price if contingent_tp else None,
        )

    def get_contingent_info(self, order_id: str, symbol: Symbol) -> ContingentInfoDto | None:
        key = (order_id, symbol)
        return self.database.get(key, None)

    def delete_contingent_info(self, order_id: str, symbol: Symbol) -> None:
        key = (order_id, symbol)
        self.database.pop(key, None)

    def get_pending_contingent_infos(self) -> list[ContingentInfoDto]:
        return [info for info in self.database.values() if not info.is_triggered]

    def mark_contingent_info_as_triggered(self, order_id: str, symbol: Symbol) -> None:
        key = (order_id, symbol)
        info = self.database.get(key, None)
        if info:
            info.is_triggered = True

    def is_liquidated_by_contingent(self, order_id: str, symbol: Symbol) -> bool:
        key = (order_id, symbol)
        info = self.database.get(key, None)
        if info:
            return info.is_triggered
        return False

    def delete_pending_contingent_infos(self, symbol: Symbol, side: PositionSide) -> None:
        self.database = {
            key: info
            for key, info in self.database.items()
            if not (info.symbol == symbol and info.side == side and not info.is_triggered)
        }

    def get_all_contingent_infos(self) -> list[ContingentInfoDto]:
        return list(self.database.values())


class ContingentInfoDBRepository(ContingentInfoBaseRepository):
    def __init__(self, session_factory: DBSessionFactory, testnet: bool, user_id: str) -> None:
        self.testnet = testnet
        self.session_factory = session_factory
        super().__init__(user_id=user_id)

    @property
    def session(self) -> Session:
        return self.session_factory.scoped_session()

    def create_contingent_info(
        self,
        order_id: str,
        symbol: Symbol,
        side: PositionSide,
        contingent_sl: ContingentOrder | None = None,
        contingent_tp: ContingentOrder | None = None,
    ) -> None:
        contingent_info = ContingentInfo(
            order_id=order_id,
            side=side,
            user_id=self.user_id,
            symbol=symbol,
            testnet=self.testnet,
            sl_trigger_price=contingent_sl.triggerPrice if contingent_sl else None,
            sl_execute_price=contingent_sl.price if contingent_sl else None,
            tp_trigger_price=contingent_tp.triggerPrice if contingent_tp else None,
            tp_execute_price=contingent_tp.price if contingent_tp else None,
        )
        self.session.add(contingent_info)
        self.session.commit()

    def get_contingent_info(self, order_id: str, symbol: Symbol) -> ContingentInfoDto | None:
        info = self.session.execute(
            select(ContingentInfo)
            .where(ContingentInfo.user_id == self.user_id)
            .where(ContingentInfo.order_id == order_id)
            .where(ContingentInfo.symbol == symbol)
            .where(ContingentInfo.testnet == self.testnet)
        ).scalar_one_or_none()
        return ContingentInfoDto.model_validate(info) if info else None

    def delete_contingent_info(self, order_id: str, symbol: Symbol) -> None:
        self.session.execute(
            delete(ContingentInfo)
            .where(ContingentInfo.user_id == self.user_id)
            .where(ContingentInfo.order_id == order_id)
            .where(ContingentInfo.symbol == symbol)
            .where(ContingentInfo.testnet == self.testnet)
        )
        self.session.commit()

    def get_pending_contingent_infos(self) -> list[ContingentInfoDto]:
        infos = (
            self.session.execute(
                select(ContingentInfo)
                .where(ContingentInfo.user_id == self.user_id)
                .where(ContingentInfo.testnet == self.testnet)
                .where(ContingentInfo.is_triggered != True)  # noqa: E712
            )
            .scalars()
            .all()
        )
        return [ContingentInfoDto.model_validate(info) for info in infos]

    def get_all_contingent_infos(self) -> list[ContingentInfoDto]:
        infos = (
            self.session.execute(
                select(ContingentInfo)
                .where(ContingentInfo.user_id == self.user_id)
                .where(ContingentInfo.testnet == self.testnet)
            )
            .scalars()
            .all()
        )
        return [ContingentInfoDto.model_validate(info) for info in infos]

    def mark_contingent_info_as_triggered(self, order_id: str, symbol: Symbol) -> None:
        self.session.execute(
            update(ContingentInfo)
            .where(ContingentInfo.user_id == self.user_id)
            .where(ContingentInfo.order_id == order_id)
            .where(ContingentInfo.symbol == symbol)
            .where(ContingentInfo.testnet == self.testnet)
            .values(is_triggered=True)
        )
        self.session.commit()

    def is_liquidated_by_contingent(self, order_id: str, symbol: Symbol) -> bool:
        info = self.session.execute(
            select(ContingentInfo)
            .where(ContingentInfo.user_id == self.user_id)
            .where(ContingentInfo.order_id == order_id)
            .where(ContingentInfo.symbol == symbol)
            .where(ContingentInfo.testnet == self.testnet)
        ).scalar_one_or_none()
        return info.is_triggered if info else False

    def delete_pending_contingent_infos(self, symbol: Symbol, side: PositionSide) -> None:
        self.session.execute(
            delete(ContingentInfo)
            .where(ContingentInfo.user_id == self.user_id)
            .where(ContingentInfo.symbol == symbol)
            .where(ContingentInfo.testnet == self.testnet)
            .where(ContingentInfo.side == side)
            .where(ContingentInfo.is_triggered != True)  # noqa: E712
        )
        self.session.commit()
