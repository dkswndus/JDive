"""인증 API: Google 로그인, 로그아웃, 현재 사용자."""

import logging
import uuid
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import (
    SESSION_COOKIE,
    clear_session_cookie,
    cookie_secure,
    get_app_settings,
    get_current_user,
    hash_token,
    issue_session,
)
from app.config import Settings
from app.db import get_db
from app.errors import AppError
from app.google_oidc import (
    HANDSHAKE_MAX_AGE_SECONDS,
    GoogleIdentity,
    OidcError,
    authorization_url,
    exchange_code,
    get_http_client,
    is_configured,
    new_handshake,
    read_handshake,
    sign_handshake,
    verify_id_token,
)
from app.models import AuthSession, User

logger = logging.getLogger(__name__)
router = APIRouter()

OAUTH_COOKIE = "jdive_oauth"
OAUTH_COOKIE_PATH = "/api/v1/auth/google"

SettingsDep = Annotated[Settings, Depends(get_app_settings)]
DbDep = Annotated[Session, Depends(get_db)]
HttpClientDep = Annotated[httpx.Client, Depends(get_http_client)]


class MeResponse(BaseModel):
    id: uuid.UUID
    email: str


def _require_configured(settings: Settings) -> None:
    if not is_configured(settings):
        raise AppError(503, "auth_not_configured", "로그인 설정이 아직 준비되지 않았습니다.")


def _redirect(url: str) -> RedirectResponse:
    response = RedirectResponse(url, status_code=302)
    response.headers["Cache-Control"] = "no-store"
    return response


def _upsert_user(db: Session, identity: GoogleIdentity) -> User:
    user = db.scalar(select(User).where(User.google_sub == identity.sub))
    if user is None:
        user = User(email=identity.email, google_sub=identity.sub)
        db.add(user)
    else:
        user.email = identity.email
    try:
        db.flush()
    except IntegrityError:  # 같은 이메일을 이미 다른 계정이 쓰고 있다
        db.rollback()
        raise OidcError("account_conflict") from None
    return user


def _authenticate(
    request: Request,
    settings: Settings,
    db: Session,
    client: httpx.Client,
    code: str | None,
    state: str | None,
    error: str | None,
) -> User:
    handshake = read_handshake(settings, request.cookies.get(OAUTH_COOKIE), state)
    if error:
        raise OidcError("access_denied" if error == "access_denied" else "invalid_request")
    if not code:
        raise OidcError("invalid_request")
    id_token = exchange_code(client, settings, code, handshake.verifier)
    identity = verify_id_token(client, settings, id_token, handshake.nonce)
    return _upsert_user(db, identity)


@router.get("/auth/google/login")
def google_login(settings: SettingsDep) -> RedirectResponse:
    _require_configured(settings)
    handshake = new_handshake()
    response = _redirect(authorization_url(settings, handshake))
    response.set_cookie(
        OAUTH_COOKIE,
        sign_handshake(settings, handshake),
        max_age=HANDSHAKE_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=cookie_secure(settings),
        path=OAUTH_COOKIE_PATH,
    )
    return response


@router.get("/auth/google/callback")
def google_callback(
    request: Request,
    settings: SettingsDep,
    db: DbDep,
    client: HttpClientDep,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    _require_configured(settings)
    try:
        user = _authenticate(request, settings, db, client, code, state, error)
    except OidcError as exc:
        db.rollback()
        logger.warning("google login rejected: %s", exc.code)
        response = _redirect(f"/login?error={exc.code}")
    else:
        response = _redirect("/")
        issue_session(db, user, settings, response)
        db.commit()
    # 성공이든 실패든 임시 쿠키는 한 번 쓰고 지운다.
    response.delete_cookie(
        OAUTH_COOKIE,
        path=OAUTH_COOKIE_PATH,
        secure=cookie_secure(settings),
        httponly=True,
        samesite="lax",
    )
    return response


@router.post("/auth/logout", status_code=204)
def logout(request: Request, settings: SettingsDep, db: DbDep) -> Response:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == hash_token(token)))
        db.commit()
    response = Response(status_code=204)
    clear_session_cookie(response, settings)
    return response


@router.get("/me")
def me(user: Annotated[User, Depends(get_current_user)]) -> MeResponse:
    return MeResponse(id=user.id, email=user.email)


@router.delete("/me", status_code=204)
def delete_me(
    user: Annotated[User, Depends(get_current_user)], settings: SettingsDep, db: DbDep
) -> Response:
    """계정 삭제. 사용자 행만 지우면 소유 데이터와 세션은 DB 의 ON DELETE CASCADE 가 지운다."""
    db.execute(delete(User).where(User.id == user.id))
    db.commit()
    response = Response(status_code=204)
    clear_session_cookie(response, settings)
    return response
