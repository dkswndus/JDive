import os
from typing import Annotated

import pytest
from alembic import command
from fastapi import APIRouter, Body
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.config import Settings
from app.errors import AppError
from app.main import create_app
from tests.db_utils import (
    ALL_TABLES,
    DEFAULT_TEST_DATABASE_URL,
    alembic_config,
    ensure_database,
)

# 이력서·JD 원문을 대신하는 가상 문자열. 로그·오류 수집·응답 어디에도 나타나면 안 된다.
SENTINEL = "SENTINEL-JD-9f3a7c"


class _Body(BaseModel):
    jd_text: str = Field(max_length=10)


def _test_router() -> APIRouter:
    router = APIRouter(prefix="/_t")

    @router.post("/validate")
    def validate(body: _Body) -> dict:
        return {"ok": True}

    @router.get("/app-error")
    def app_error() -> dict:
        raise AppError(
            409,
            "duplicate_posting",
            "이미 저장한 공고입니다.",
            extra={"existing_posting_id": "abc"},
        )

    @router.get("/boom")
    def boom() -> dict:
        jd_text = SENTINEL  # 지역 변수에 원문이 들어 있는 상황
        raise RuntimeError(f"처리 실패: {jd_text}")

    @router.post("/boom-body")
    def boom_body(payload: Annotated[dict, Body()]) -> dict:
        jd_text = payload["jd_text"]  # 요청 본문의 원문이 지역 변수와 예외 메시지에 들어간다
        raise RuntimeError(f"처리 실패: {jd_text}")

    return router


@pytest.fixture
def app():
    application = create_app(Settings(_env_file=None))
    application.include_router(_test_router())
    return application


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(scope="session")
def database_url() -> str:
    return os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)


@pytest.fixture(scope="session")
def migrated_engine(database_url):
    """마이그레이션을 처음부터 적용한 테스트 DB. 세션당 한 번만 만든다."""
    url = ensure_database(database_url)
    config = alembic_config(url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine = create_engine(url)
    yield engine
    engine.dispose()


@pytest.fixture
def db(migrated_engine):
    """테스트마다 새 세션을 주고, 끝나면 모든 테이블을 비운다."""
    with Session(migrated_engine) as session:
        yield session
    with migrated_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {ALL_TABLES} RESTART IDENTITY CASCADE"))  # noqa: S608
