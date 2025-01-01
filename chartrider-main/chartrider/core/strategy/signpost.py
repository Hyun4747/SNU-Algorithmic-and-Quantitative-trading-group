from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from pydantic import BaseModel

if TYPE_CHECKING:
    from chartrider.core.common.repository.models import Symbol

SignpostID = str


class Signpost(BaseModel):
    name: str
    symbol: str
    description: str | None
    timestamp: int
    info: dict[str, Any] = {}


class Signposter:
    def __init__(self) -> None:
        self.__signposts: dict[SignpostID, list[Signpost]] = defaultdict(list)

    def get_signposts(self) -> dict[SignpostID, list[Signpost]]:
        return self.__signposts

    def begin_interval(
        self,
        signpost_id: SignpostID,
        symbol: Symbol,
        name: str,
        timestamp: int,
        description: str | None = None,
        **kwargs: Any,
    ):
        if signpost_id in self.__signposts:
            raise ValueError(f"Signpost {signpost_id} already exists")
        signpost = Signpost(
            name=name,
            symbol=symbol,
            description=description,
            timestamp=timestamp,
            info=kwargs,
        )
        self.__signposts[signpost_id] = [signpost]

    def end_interval(
        self,
        signpost_id: SignpostID,
        symbol: Symbol,
        timestamp: int,
        name: str | None = None,
        description: str | None = None,
        **kwargs: Any,
    ) -> None:
        if signpost_id not in self.__signposts:
            return
        begin_signpost = self.__signposts[signpost_id][0]
        signpost = Signpost(
            name=name or begin_signpost.name,
            symbol=symbol,
            description=description or begin_signpost.description,
            timestamp=timestamp,
            info=kwargs,
        )
        self.__signposts[signpost_id].append(signpost)

    def emit_event(
        self,
        name: str,
        timestamp: int,
        description: str | None = None,
        **kwargs: Any,
    ) -> None:
        signpost_id = str(uuid4())
        signpost = Signpost(
            name=name,
            symbol="",
            description=description,
            timestamp=timestamp,
            info=kwargs,
        )
        self.__signposts[signpost_id] = [signpost]
