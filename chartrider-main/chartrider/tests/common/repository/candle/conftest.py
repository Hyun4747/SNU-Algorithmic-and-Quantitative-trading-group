import pytest

from chartrider.core.common.repository import CandleDBRepository
from chartrider.database.connection import DBSessionFactory


@pytest.fixture
def candle_db_repository(db_session_factory: DBSessionFactory) -> CandleDBRepository:
    return CandleDBRepository(db_session_factory)
