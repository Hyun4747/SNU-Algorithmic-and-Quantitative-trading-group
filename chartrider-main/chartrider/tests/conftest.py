from typing import Iterable

import pytest
import sqlalchemy
from pytest_mock import MockFixture
from sqlalchemy import orm

from chartrider.database.base import DeclarativeBase
from chartrider.database.connection import DBSessionFactory
from chartrider.settings import postgres_settings as db_config


@pytest.fixture(scope="session")
def db_engine() -> Iterable[sqlalchemy.Engine]:
    url = db_config.test_url
    engine = sqlalchemy.create_engine(url, echo=True)
    DeclarativeBase.metadata.create_all(bind=engine)

    try:
        yield engine
    finally:
        DeclarativeBase.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine: sqlalchemy.Engine) -> Iterable[orm.Session]:
    connection = db_engine.connect()
    transaction = connection.begin_nested()

    session_maker = orm.sessionmaker(
        connection,
        expire_on_commit=True,
    )

    session = session_maker()

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture(scope="function")
def db_session_factory(mocker: MockFixture, db_session: orm.Session) -> DBSessionFactory:
    db_session_factory = DBSessionFactory()
    method_to_patch = db_session_factory.scoped_session
    mocker.patch.object(method_to_patch.__self__, method_to_patch.__name__, return_value=db_session)
    return db_session_factory
