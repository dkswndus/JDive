from collections.abc import Iterator
from functools import lru_cache

from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


@lru_cache
def _sessionmaker(database_url: str) -> sessionmaker[Session]:
    engine = create_engine(database_url, pool_pre_ping=True)
    return sessionmaker(engine, expire_on_commit=False)


def get_db(request: Request) -> Iterator[Session]:
    """요청 하나에 세션 하나를 준다. 접속 대상은 create_app 에 준 Settings 를 따른다."""
    with _sessionmaker(request.app.state.settings.database_url)() as session:
        yield session
