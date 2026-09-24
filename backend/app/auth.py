"""세션 쿠키, 현재 사용자, 상태 변경 요청의 Origin 검증."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import get_db
from app.errors import AppError
from app.models import AuthSession, User

SESSION_COOKIE = "jdive_session"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
LAST_SEEN_REFRESH = timedelta(hours=1)  # 요청마다 쓰지 않도록, 이만큼 지났을 때만 갱신한다


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def cookie_secure(settings: Settings) -> bool:
    return settings.public_base_url.lower().startswith("https://")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_session(db: Session, user: User, settings: Settings, response: Response) -> None:
    """DB 에는 토큰의 해시만 저장하고, 토큰 원문은 쿠키로만 내보낸다."""
    token = secrets.token_urlsafe(32)
    ttl = timedelta(days=settings.session_ttl_days)
    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=datetime.now(UTC) + ttl,
        )
    )
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(ttl.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=cookie_secure(settings),
        path="/",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        secure=cookie_secure(settings),
        httponly=True,
        samesite="lax",
    )


def get_current_user(request: Request, db: Annotated[Session, Depends(get_db)]) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    row = None
    if token:
        row = db.execute(
            select(User, AuthSession)
            .join(AuthSession, AuthSession.user_id == User.id)
            .where(
                AuthSession.token_hash == hash_token(token),
                AuthSession.expires_at > datetime.now(UTC),
            )
        ).first()
    if row is None:
        raise AppError(401, "unauthorized", "로그인이 필요합니다.")

    user, session = row
    now = datetime.now(UTC)
    if now - session.last_seen_at > LAST_SEEN_REFRESH:
        session.last_seen_at = now
        db.commit()
    return user


def origin_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}".lower()


def require_same_origin(request: Request) -> None:
    """상태를 바꾸는 요청은 Origin 이 PUBLIC_BASE_URL 의 출처와 같아야 한다(CSRF 방어)."""
    if request.method in SAFE_METHODS:
        return
    expected = origin_of(get_app_settings(request).public_base_url)
    if request.headers.get("origin") != expected:
        raise AppError(403, "csrf_origin_mismatch", "허용되지 않은 출처의 요청입니다.")
