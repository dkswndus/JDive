"""Google OIDC(인가 코드 + PKCE) 로그인. HTTP 라우팅은 모른다.

실패는 OidcError 로만 알린다. 코드 문자열 외에는 아무것도 담지 않는다(토큰·응답 본문·code 금지).
"""

import logging
import secrets
from collections.abc import Iterator
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from authlib.oauth2.rfc7636 import create_s256_code_challenge
from itsdangerous import BadSignature, URLSafeTimedSerializer
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet

from app.config import Settings

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105  (엔드포인트 URL 이지 비밀번호가 아니다)
JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
ISSUERS = ["https://accounts.google.com", "accounts.google.com"]
ALGORITHMS = ["RS256"]  # 알고리즘을 고정해 none·HS256 혼동 공격을 막는다

HANDSHAKE_MAX_AGE_SECONDS = 600
HANDSHAKE_SALT = "jdive-oauth-handshake"
MIN_SESSION_SECRET_LENGTH = 32
HTTP_TIMEOUT_SECONDS = 10.0
MAX_EMAIL_LENGTH = 320  # users.email, users.google_sub 컬럼 길이와 같다
MAX_SUB_LENGTH = 255

logger = logging.getLogger(__name__)


class OidcError(Exception):
    """로그인 실패. code 는 `/login?error=` 로 그대로 전달되는 짧은 식별자다."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Handshake:
    """로그인 시작 때 만들어 서명 쿠키에 담아 두는 값. 콜백에서 다시 꺼내 대조한다."""

    state: str
    nonce: str
    verifier: str


@dataclass(frozen=True)
class GoogleIdentity:
    sub: str
    email: str


def get_http_client() -> Iterator[httpx.Client]:
    with httpx.Client(timeout=HTTP_TIMEOUT_SECONDS) as client:
        yield client


def is_configured(settings: Settings) -> bool:
    return (
        len(settings.session_secret) >= MIN_SESSION_SECRET_LENGTH
        and bool(settings.google_client_id)
        and bool(settings.google_client_secret)
    )


def redirect_uri(settings: Settings) -> str:
    return f"{settings.public_base_url.rstrip('/')}/api/v1/auth/google/callback"


def new_handshake() -> Handshake:
    return Handshake(
        state=secrets.token_urlsafe(32),
        nonce=secrets.token_urlsafe(32),
        verifier=secrets.token_urlsafe(64),  # RFC 7636: 43~128자
    )


def authorization_url(settings: Settings, handshake: Handshake) -> str:
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri(settings),
        "response_type": "code",
        "scope": "openid email",
        "state": handshake.state,
        "nonce": handshake.nonce,
        "code_challenge": create_s256_code_challenge(handshake.verifier),
        "code_challenge_method": "S256",
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.session_secret, salt=HANDSHAKE_SALT)


def sign_handshake(settings: Settings, handshake: Handshake) -> str:
    payload = {"s": handshake.state, "n": handshake.nonce, "v": handshake.verifier}
    return _serializer(settings).dumps(payload)


def read_handshake(settings: Settings, cookie: str | None, state: str | None) -> Handshake:
    """임시 쿠키의 서명·만료를 확인하고, 콜백으로 돌아온 state 가 쿠키의 것과 같은지 대조한다."""
    if not cookie or not state:
        raise OidcError("invalid_state")
    try:
        data = _serializer(settings).loads(cookie, max_age=HANDSHAKE_MAX_AGE_SECONDS)
        handshake = Handshake(state=data["s"], nonce=data["n"], verifier=data["v"])
    except (BadSignature, KeyError, TypeError):
        raise OidcError("invalid_state") from None
    if not secrets.compare_digest(handshake.state, state):
        raise OidcError("invalid_state")
    return handshake


def exchange_code(client: httpx.Client, settings: Settings, code: str, verifier: str) -> str:
    """인가 코드를 ID 토큰으로 바꾼다. 응답 본문은 로그·예외에 남기지 않는다."""
    try:
        response = client.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri(settings),
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "code_verifier": verifier,
            },
        )
    except httpx.HTTPError:
        logger.warning("google token exchange failed: network")
        raise OidcError("token_exchange_failed") from None
    if response.status_code != httpx.codes.OK:
        logger.warning("google token exchange failed", extra={"status": response.status_code})
        raise OidcError("token_exchange_failed")
    try:
        id_token = response.json()["id_token"]
    except (ValueError, KeyError, TypeError):
        raise OidcError("token_exchange_failed") from None
    if not isinstance(id_token, str) or not id_token:
        raise OidcError("token_exchange_failed")
    return id_token


def verify_id_token(
    client: httpx.Client, settings: Settings, id_token: str, nonce: str
) -> GoogleIdentity:
    """서명(RS256)·iss·aud·exp·nonce·sub·email·email_verified 를 모두 확인한다."""
    # ponytail: 로그인마다 JWKS 를 새로 받는다. 로그인이 잦아지면 Cache-Control 만큼 캐시한다.
    try:
        response = client.get(JWKS_URL)
        response.raise_for_status()
        key_set = KeySet.import_key_set(response.json())
    except (httpx.HTTPError, ValueError, JoseError):
        raise OidcError("invalid_id_token") from None

    claims_registry = jwt.JWTClaimsRegistry(
        iss={"essential": True, "values": ISSUERS},
        aud={"essential": True, "value": settings.google_client_id},
        sub={"essential": True},
        exp={"essential": True},
        nonce={"essential": True, "value": nonce},
    )
    try:
        claims = jwt.decode(id_token, key_set, algorithms=ALGORITHMS).claims
        claims_registry.validate(claims)
    except (JoseError, ValueError):
        raise OidcError("invalid_id_token") from None

    sub, email = claims.get("sub"), claims.get("email")
    if not (isinstance(sub, str) and sub and isinstance(email, str) and email):
        raise OidcError("invalid_id_token")
    if len(sub) > MAX_SUB_LENGTH or len(email) > MAX_EMAIL_LENGTH:
        raise OidcError("invalid_id_token")
    if claims.get("email_verified") is not True:
        raise OidcError("email_not_verified")
    return GoogleIdentity(sub=sub, email=email.lower())
