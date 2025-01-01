import pytest

from chartrider.core.common.repository.contingent.repository import (
    ContingentInfoBaseRepository,
    ContingentInfoDBRepository,
    ContingentInfoInMemoryRepository,
)
from chartrider.database.connection import DBSessionFactory


@pytest.fixture
def contingent_repository(request):
    return request.getfixturevalue(request.param)


@pytest.fixture
def contingent_db_repository(db_session_factory: DBSessionFactory) -> ContingentInfoBaseRepository:
    return ContingentInfoDBRepository(db_session_factory, testnet=False, user_id="test")


@pytest.fixture
def contingent_inmemory_repository() -> ContingentInfoBaseRepository:
    return ContingentInfoInMemoryRepository(user_id="test")


@pytest.fixture
def contingent_repository_factory(db_session_factory: DBSessionFactory):
    return ContingentRepositoryFactory(db_session_factory)


class ContingentRepositoryFactory:
    def __init__(self, db_session_factory: DBSessionFactory):
        self.db_session_factory = db_session_factory

    def get_repository(
        self, testnet: bool, user_id: str, base_repository: ContingentInfoBaseRepository
    ) -> ContingentInfoBaseRepository:
        if isinstance(base_repository, ContingentInfoDBRepository):
            return ContingentInfoDBRepository(
                session_factory=self.db_session_factory, testnet=testnet, user_id=user_id
            )
        else:
            return ContingentInfoInMemoryRepository(user_id=user_id)
