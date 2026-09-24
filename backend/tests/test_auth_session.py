"""세션(`GET /me`, 로그아웃)과 상태 변경 요청의 Origin 검증."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from app.auth import require_same_origin
from app.config import Settings
from app.errors import register_error_handlers
from app.models import AuthSession, User
from tests.fake_google import ORIGIN, sign_in

ME = "/api/v1/me"
LOGOUT = "/api/v1/auth/logout"
UNSAFE_METHODS = ["POST", "PUT", "PATCH", "DELETE"]


def session_count(db) -> int:
    return db.scalar(select(func.count()).select_from(AuthSession))


# ---- GET /me ---------------------------------------------------------------


def test_me_requires_a_session(auth_client):
    response = auth_client.get(ME)

    assert response.status_code == 401
    error = response.json()["error"]
    assert error["code"] == "unauthorized"
    assert error["request_id"]


def test_me_returns_only_id_and_email(auth_client, fake_google, db):
    sign_in(auth_client, fake_google)
    user = db.scalar(select(User))

    response = auth_client.get(ME)

    assert response.status_code == 200
    assert response.json() == {"id": str(user.id), "email": "user@example.com"}


def test_each_session_sees_its_own_user(make_auth_client, fake_google):
    first, second = make_auth_client(), make_auth_client()
    sign_in(first, fake_google)
    fake_google.sub, fake_google.email = "google-sub-2", "second@example.com"
    sign_in(second, fake_google)

    assert first.get(ME).json()["email"] == "user@example.com"
    assert second.get(ME).json()["email"] == "second@example.com"


def test_me_rejects_unknown_token(auth_client):
    response = auth_client.get(ME, headers={"Cookie": "jdive_session=not-a-real-token"})

    assert response.status_code == 401


def test_me_rejects_expired_session(auth_client, fake_google, db):
    sign_in(auth_client, fake_google)
    db.execute(update(AuthSession).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    db.commit()

    assert auth_client.get(ME).status_code == 401


def test_last_seen_is_refreshed_only_when_stale(auth_client, fake_google, db):
    sign_in(auth_client, fake_google)
    stale = datetime.now(UTC) - timedelta(days=1)
    db.execute(update(AuthSession).values(last_seen_at=stale))
    db.commit()

    auth_client.get(ME)
    db.expire_all()
    refreshed = db.scalar(select(AuthSession.last_seen_at))
    assert refreshed > stale + timedelta(hours=23)

    auth_client.get(ME)
    db.expire_all()
    assert db.scalar(select(AuthSession.last_seen_at)) == refreshed  # 요청마다 쓰지 않는다


# ---- POST /auth/logout -------------------------------------------------------


def test_logout_deletes_session_and_clears_cookie(auth_client, fake_google, db):
    sign_in(auth_client, fake_google)

    response = auth_client.post(LOGOUT, headers={"Origin": ORIGIN})

    assert response.status_code == 204
    assert session_count(db) == 0
    assert auth_client.cookies.get("jdive_session") is None
    assert auth_client.get(ME).status_code == 401


def test_logout_only_ends_the_current_session(make_auth_client, fake_google, db):
    first, second = make_auth_client(), make_auth_client()
    sign_in(first, fake_google)
    sign_in(second, fake_google)

    first.post(LOGOUT, headers={"Origin": ORIGIN})

    assert second.get(ME).status_code == 200
    assert session_count(db) == 1


def test_logout_without_a_session_still_succeeds(auth_client):
    assert auth_client.post(LOGOUT, headers={"Origin": ORIGIN}).status_code == 204


def test_logout_from_a_foreign_origin_is_rejected_and_keeps_the_session(
    auth_client, fake_google, db
):
    sign_in(auth_client, fake_google)

    response = auth_client.post(LOGOUT, headers={"Origin": "http://evil.example.com"})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_origin_mismatch"
    assert session_count(db) == 1
    assert auth_client.get(ME).status_code == 200


# ---- Origin 검증 ---------------------------------------------------------------


def origin_client(public_base_url: str = ORIGIN) -> TestClient:
    """`require_same_origin` 만 붙인 최소 앱. 모든 메서드에 같은 경로를 연다."""
    application = FastAPI(dependencies=[Depends(require_same_origin)])
    application.state.settings = Settings(_env_file=None, public_base_url=public_base_url)
    register_error_handlers(application)

    def endpoint() -> dict[str, bool]:
        return {"ok": True}

    for method in ["GET", *UNSAFE_METHODS]:
        application.add_api_route("/x", endpoint, methods=[method])
    return TestClient(application)


@pytest.mark.parametrize("method", UNSAFE_METHODS)
@pytest.mark.parametrize(
    "origin",
    [
        None,
        "null",
        "http://evil.example.com",
        "http://localhost:3001",
        "https://localhost:3000",
        "http://localhost:3000.evil.com",
    ],
    ids=["missing", "null", "foreign-host", "other-port", "other-scheme", "suffix-trick"],
)
def test_unsafe_methods_reject_missing_or_foreign_origin(method, origin):
    headers = {} if origin is None else {"Origin": origin}

    response = origin_client().request(method, "/x", headers=headers)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_origin_mismatch"


@pytest.mark.parametrize("method", UNSAFE_METHODS)
def test_unsafe_methods_accept_the_public_origin(method):
    assert origin_client().request(method, "/x", headers={"Origin": ORIGIN}).status_code == 200


def test_safe_requests_do_not_need_an_origin():
    client = origin_client()

    assert client.get("/x").status_code == 200
    assert client.get("/x", headers={"Origin": "http://evil.example.com"}).status_code == 200


def test_origin_matching_ignores_case_and_trailing_slash_of_the_configured_url():
    client = origin_client("HTTP://LocalHost:3000/")

    assert client.post("/x", headers={"Origin": ORIGIN}).status_code == 200
