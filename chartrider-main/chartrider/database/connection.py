from contextvars import ContextVar

import sqlalchemy
from sqlalchemy import orm
from sqlalchemy.orm import scoped_session

from chartrider.settings import postgres_settings as db_config


class DBSessionFactory:
    __session_ctx: ContextVar[orm.Session] = ContextVar("session")

    def __init__(self):
        self.__engine: sqlalchemy.Engine = sqlalchemy.create_engine(
            db_config.url,
            max_overflow=db_config.max_pool_size,
            pool_pre_ping=db_config.pool_pre_ping,
        )
        self.__session_maker = orm.sessionmaker(bind=self.__engine, expire_on_commit=False)
        self.__make_scoped_session = scoped_session(self.__session_maker)

    def scoped_session(self) -> orm.Session:
        session = DBSessionFactory.__session_ctx.get(None)
        if session is None:
            session = self.__make_scoped_session()
            DBSessionFactory.__session_ctx.set(session)
        return session

    def teardown(self):
        orm.close_all_sessions()
        self.__engine.dispose()
