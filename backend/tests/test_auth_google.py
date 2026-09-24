"""Google 로그인(OIDC) 흐름: 로그인 시작, 콜백, PKCE·state·nonce·ID 토큰 검증."""

import hashlib
import logging
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy import func, select

from app import google_oidc
from app.models import AuthSession, User
from tests.fake_google import CLIENT_ID, CLIENT_SECRET, REDIRECT_URI, sign_in

LOGIN = "/api/v1/auth/google/login"
CALLBACK = "/api/v1/auth/google/callback"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"


def query(location: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlsplit(location).query).items()}


def set_cookie(response, name: str) -> str:
    headers = response.headers.get_list("set-cookie")
    return next(h for h in headers if h.startswith(f"{name}=")).lower()


def count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


def start(client, fake) -> tuple[str, str]:
    """로그인을 시작하고, Google 이 돌려줄 (code, state) 를 돌려준다."""
    return fake.authorize(client.get(LOGIN).headers["location"])


def finish(client, code: str, state: str, **extra):
    return client.get(CALLBACK, params={"code": code, "state": state, **extra})


def assert_rejected(client, db, response, code: str) -> None:
    """콜백이 오류로 끝났다: 로그인 화면으로 보내고 사용자·세션·쿠키를 만들지 않는다."""
    assert response.status_code == 302
    assert response.headers["location"] == f"/login?error={code}"
    assert count(db, User) == 0
    assert count(db, AuthSession) == 0
    assert client.cookies.get("jdive_session") is None
    assert client.cookies.get("jdive_oauth") is None  # 실패한 시도의 임시 쿠키도 지운다


# ---- 로그인 시작 ----------------------------------------------------------


def test_login_redirects_to_google_with_pkce_state_and_nonce(auth_client):
    response = auth_client.get(LOGIN)

    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith(GOOGLE_AUTH_URL + "?")
    params = query(location)
    assert params["response_type"] == "code"
    assert params["client_id"] == CLIENT_ID
    assert params["redirect_uri"] == REDIRECT_URI
    assert params["scope"] == "openid email"
    assert params["code_challenge_method"] == "S256"
    assert len(params["code_challenge"]) == 43  # SHA-256 을 base64url 로 인코딩한 길이
    assert len(params["state"]) >= 32
    assert len(params["nonce"]) >= 32
    assert "code_verifier" not in params
    assert CLIENT_SECRET not in location
    assert response.headers["cache-control"] == "no-store"


def test_login_sets_signed_short_lived_handshake_cookie(auth_client):
    cookie = set_cookie(auth_client.get(LOGIN), "jdive_oauth")

    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "max-age=600" in cookie
    assert "path=/api/v1/auth/google" in cookie
    assert "; secure" not in cookie  # 테스트 환경의 PUBLIC_BASE_URL 은 http 다


def test_login_values_change_every_attempt(auth_client):
    first, second = (query(auth_client.get(LOGIN).headers["location"]) for _ in range(2))

    for name in ("state", "nonce", "code_challenge"):
        assert first[name] != second[name]


def test_cookies_are_secure_when_public_url_is_https(make_auth_client, fake_google):
    https_origin = "https://jdive.example.com"
    fake_google.redirect_uri = f"{https_origin}/api/v1/auth/google/callback"
    client = make_auth_client(base_url="https://testserver", public_base_url=https_origin)

    login = client.get(LOGIN)
    assert query(login.headers["location"])["redirect_uri"] == fake_google.redirect_uri
    assert "; secure" in set_cookie(login, "jdive_oauth")

    code, state = fake_google.authorize(login.headers["location"])
    callback = finish(client, code, state)
    assert callback.headers["location"] == "/"
    assert "; secure" in set_cookie(callback, "jdive_session")


@pytest.mark.parametrize(
    "overrides",
    [
        {"session_secret": ""},
        {"session_secret": "too-short"},
        {"google_client_id": ""},
        {"google_client_secret": ""},
    ],
    ids=["no-session-secret", "short-session-secret", "no-client-id", "no-client-secret"],
)
def test_login_refuses_to_start_when_not_configured(make_auth_client, overrides):
    response = make_auth_client(**overrides).get(LOGIN)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "auth_not_configured"
    assert not response.headers.get_list("set-cookie")


# ---- 콜백 성공 ------------------------------------------------------------


def test_callback_creates_user_and_session_then_redirects_home(auth_client, fake_google, db):
    response = sign_in(auth_client, fake_google)

    assert response.status_code == 302
    assert response.headers["location"] == "/"
    assert response.headers["cache-control"] == "no-store"

    user = db.scalar(select(User))
    assert (user.google_sub, user.email) == ("google-sub-1", "user@example.com")

    session = db.scalar(select(AuthSession))
    token = auth_client.cookies.get("jdive_session")
    assert session.user_id == user.id
    assert session.token_hash == hashlib.sha256(token.encode()).hexdigest()
    assert session.token_hash != token  # 토큰 원문은 DB 에 없다
    lifetime = session.expires_at - datetime.now(UTC)
    assert timedelta(days=13, hours=23) < lifetime <= timedelta(days=14)

    cookie = set_cookie(response, "jdive_session")
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert f"max-age={14 * 24 * 3600}" in cookie
    assert re.search(r"path=/(;|$)", cookie)
    assert auth_client.cookies.get("jdive_oauth") is None  # 임시 쿠키는 쓰고 나면 지운다


def test_token_request_carries_pkce_verifier_and_client_credentials(auth_client, fake_google):
    sign_in(auth_client, fake_google)

    (request,) = fake_google.token_requests
    assert request["grant_type"] == "authorization_code"
    assert request["client_id"] == CLIENT_ID
    assert request["client_secret"] == CLIENT_SECRET
    assert request["redirect_uri"] == REDIRECT_URI
    assert len(request["code_verifier"]) >= 43  # RFC 7636: 43~128자
    # verifier 와 challenge 의 S256 일치는 가짜 Google 이 검사한다. 어긋나면 로그인이 실패한다.


def test_login_fails_when_pkce_challenge_does_not_match_verifier(auth_client, fake_google, db):
    location = auth_client.get(LOGIN).headers["location"]
    tampered = location.replace(query(location)["code_challenge"], "A" * 43)
    code, state = fake_google.authorize(tampered)

    response = finish(auth_client, code, state)

    assert_rejected(auth_client, db, response, "token_exchange_failed")


def test_callback_accepts_legacy_google_issuer(auth_client, fake_google):
    fake_google.claims = {"iss": "accounts.google.com"}

    assert sign_in(auth_client, fake_google).headers["location"] == "/"


def test_repeat_login_reuses_user_and_updates_email(auth_client, fake_google, db):
    sign_in(auth_client, fake_google)
    fake_google.email = "renamed@example.com"
    sign_in(auth_client, fake_google)

    assert count(db, User) == 1
    assert db.scalar(select(User.email)) == "renamed@example.com"
    assert count(db, AuthSession) == 2


def test_email_is_stored_in_lowercase(auth_client, fake_google, db):
    fake_google.email = "Mixed.Case@Example.COM"

    sign_in(auth_client, fake_google)

    assert db.scalar(select(User.email)) == "mixed.case@example.com"


def test_login_is_rejected_when_email_belongs_to_another_account(auth_client, fake_google, db):
    db.add(User(email="user@example.com", google_sub="someone-else"))
    db.commit()

    response = sign_in(auth_client, fake_google)

    assert response.headers["location"] == "/login?error=account_conflict"
    assert count(db, User) == 1
    assert count(db, AuthSession) == 0
    assert auth_client.cookies.get("jdive_session") is None


# ---- state·임시 쿠키 -------------------------------------------------------


def test_callback_rejects_state_that_differs_from_the_cookie(auth_client, fake_google, db):
    code, _ = start(auth_client, fake_google)

    response = finish(auth_client, code, "forged-state")

    assert_rejected(auth_client, db, response, "invalid_state")
    assert fake_google.token_requests == []  # Google 에 코드를 보내기 전에 막는다


def test_callback_rejects_a_login_started_in_another_browser(make_auth_client, fake_google, db):
    """공격자가 자기 로그인 결과(code·state)를 피해자 브라우저에 심는 로그인 CSRF."""
    attacker, victim = make_auth_client(), make_auth_client()
    code, state = start(attacker, fake_google)
    victim.get(LOGIN)

    response = finish(victim, code, state)

    assert_rejected(victim, db, response, "invalid_state")
    assert fake_google.token_requests == []


def test_callback_rejects_missing_handshake_cookie(auth_client, fake_google, db):
    code, state = start(auth_client, fake_google)
    auth_client.cookies.clear()

    response = finish(auth_client, code, state)

    assert_rejected(auth_client, db, response, "invalid_state")
    assert fake_google.token_requests == []


# 서명의 마지막 글자는 base64 의 미사용 비트라, 바꿔도 같은 서명으로 읽히는 경우가 있다(약 6%).
# 그래서 페이로드의 첫 글자와 서명 중간 글자를 바꾼다.
@pytest.mark.parametrize("position", [0, -10], ids=["payload", "signature"])
def test_callback_rejects_tampered_handshake_cookie(auth_client, fake_google, db, position):
    code, state = start(auth_client, fake_google)
    for cookie in auth_client.cookies.jar:
        if cookie.name == "jdive_oauth":
            i = position % len(cookie.value)
            replacement = "A" if cookie.value[i] != "A" else "B"
            cookie.value = cookie.value[:i] + replacement + cookie.value[i + 1 :]

    response = finish(auth_client, code, state)

    assert_rejected(auth_client, db, response, "invalid_state")
    assert fake_google.token_requests == []


def test_callback_rejects_expired_handshake(auth_client, fake_google, db, monkeypatch):
    code, state = start(auth_client, fake_google)
    monkeypatch.setattr(google_oidc, "HANDSHAKE_MAX_AGE_SECONDS", -1)

    response = finish(auth_client, code, state)

    assert_rejected(auth_client, db, response, "invalid_state")
    assert fake_google.token_requests == []


# ---- Google 이 돌려준 오류 ---------------------------------------------------


def test_callback_stops_when_user_denies_consent(auth_client, fake_google, db):
    _, state = start(auth_client, fake_google)

    response = auth_client.get(CALLBACK, params={"error": "access_denied", "state": state})

    assert_rejected(auth_client, db, response, "access_denied")
    assert fake_google.token_requests == []


def test_callback_rejects_missing_code(auth_client, fake_google, db):
    _, state = start(auth_client, fake_google)

    response = auth_client.get(CALLBACK, params={"state": state})

    assert_rejected(auth_client, db, response, "invalid_request")
    assert fake_google.token_requests == []


def test_callback_reports_token_endpoint_failure(auth_client, fake_google, db):
    code, state = start(auth_client, fake_google)
    fake_google.token_status = 500

    assert_rejected(auth_client, db, finish(auth_client, code, state), "token_exchange_failed")


def test_callback_rejects_code_google_did_not_issue(auth_client, fake_google, db):
    _, state = start(auth_client, fake_google)

    response = finish(auth_client, "never-issued", state)

    assert_rejected(auth_client, db, response, "token_exchange_failed")


# ---- ID 토큰 검증 ------------------------------------------------------------

INVALID_ID_TOKENS = [
    pytest.param({"signer": "wrong_key"}, id="signature-from-another-key"),
    pytest.param({"signer": "unknown_kid"}, id="unknown-key-id"),
    pytest.param({"signer": "none"}, id="alg-none"),
    pytest.param({"signer": "hs256"}, id="hs256-signed-with-public-key"),
    pytest.param({"claims": {"iss": "https://evil.example.com"}}, id="wrong-issuer"),
    pytest.param({"claims": {"aud": "another-client"}}, id="wrong-audience"),
    pytest.param({"claims": {"exp": 1}}, id="expired"),
    pytest.param({"claims": {"nonce": "attacker-nonce"}}, id="nonce-mismatch"),
    pytest.param({"claims": {"nonce": None}}, id="missing-nonce"),
    pytest.param({"claims": {"sub": None}}, id="missing-sub"),
    pytest.param({"claims": {"email": None}}, id="missing-email"),
]


@pytest.mark.parametrize("case", INVALID_ID_TOKENS)
def test_callback_rejects_invalid_id_token(auth_client, fake_google, db, case):
    fake_google.signer = case.get("signer", "good")
    fake_google.claims = case.get("claims", {})

    response = sign_in(auth_client, fake_google)

    assert_rejected(auth_client, db, response, "invalid_id_token")


def test_callback_rejects_id_token_when_signing_keys_are_unavailable(auth_client, fake_google, db):
    fake_google.jwks_status = 500

    assert_rejected(auth_client, db, sign_in(auth_client, fake_google), "invalid_id_token")


@pytest.mark.parametrize(
    "claims",
    [{"email_verified": False}, {"email_verified": None}, {"email_verified": "true"}],
    ids=["false", "missing", "string"],
)
def test_callback_rejects_unverified_email(auth_client, fake_google, db, claims):
    fake_google.claims = claims

    assert_rejected(auth_client, db, sign_in(auth_client, fake_google), "email_not_verified")


# ---- 로그 ---------------------------------------------------------------------


def test_login_flow_leaves_no_secrets_in_logs(auth_client, fake_google, caplog):
    caplog.set_level(logging.DEBUG)
    location = auth_client.get(LOGIN).headers["location"]
    code, state = fake_google.authorize(location)
    finish(auth_client, code, state)
    finish(auth_client, code, "forged-state")  # 실패 경로도 함께 본다

    (request,) = fake_google.token_requests
    secrets = [
        code,
        state,
        query(location)["nonce"],
        request["code_verifier"],
        CLIENT_SECRET,
        fake_google.last_id_token,
        auth_client.cookies.get("jdive_session"),
    ]
    logs = caplog.text + "".join(str(vars(record)) for record in caplog.records)
    for secret in secrets:
        assert secret and secret not in logs
