"""Google 의 인증 서버와 JWKS 를 흉내 낸다. 실제 Google 에는 접속하지 않는다."""

import base64
import hashlib
import hmac
import json
import time
from functools import cache
from urllib.parse import parse_qs, parse_qsl, urlsplit

import httpx
from joserfc import jwt
from joserfc.jwk import KeySet, RSAKey

CLIENT_ID = "test-client.apps.googleusercontent.com"
CLIENT_SECRET = "test-client-secret"
ORIGIN = "http://localhost:3000"
REDIRECT_URI = f"{ORIGIN}/api/v1/auth/google/callback"
ISSUER = "https://accounts.google.com"
KID = "test-key"


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _new_key() -> RSAKey:
    return RSAKey.generate_key(2048, parameters={"kid": KID, "use": "sig", "alg": "RS256"})


@cache
def _keys() -> tuple[RSAKey, RSAKey]:
    """서명 키와, 같은 kid 를 쓰는 다른 키(위조 서명용). RSA 생성이 느려 한 번만 만든다."""
    return _new_key(), _new_key()


def _compact(header: dict, claims: dict) -> str:
    def part(value: dict) -> str:
        return b64url(json.dumps(value, separators=(",", ":")).encode())

    return f"{part(header)}.{part(claims)}"


class FakeGoogle:
    def __init__(self) -> None:
        self.key, self.other_key = _keys()
        self.sub = "google-sub-1"
        self.email = "user@example.com"
        self.redirect_uri = REDIRECT_URI
        self.claims: dict[str, object] = {}  # ID 토큰 클레임 덮어쓰기. 값이 None 이면 클레임을 뺀다
        self.signer = "good"  # good | wrong_key | unknown_kid | none | hs256
        self.token_status = 200
        self.jwks_status = 200
        self.token_requests: list[dict[str, str]] = []
        self.last_id_token = ""
        self._pending: dict[str, dict[str, str]] = {}

    def authorize(self, location: str) -> tuple[str, str]:
        """로그인 리디렉션 URL 을 받아, 사용자가 동의한 것처럼 (code, state) 를 돌려준다."""
        query = {k: v[0] for k, v in parse_qs(urlsplit(location).query).items()}
        code = f"code-{len(self._pending)}-{time.monotonic_ns()}"
        self._pending[code] = {"nonce": query["nonce"], "challenge": query["code_challenge"]}
        return code, query["state"]

    def handle(self, request: httpx.Request) -> httpx.Response:
        target = (request.method, request.url.host, request.url.path)
        if target == ("GET", "www.googleapis.com", "/oauth2/v3/certs"):
            if self.jwks_status != 200:
                return httpx.Response(self.jwks_status)
            return httpx.Response(200, json=KeySet([self.key]).as_dict(private=False))
        if target == ("POST", "oauth2.googleapis.com", "/token"):
            return self._token(request)
        raise AssertionError(f"예상하지 못한 요청: {request.method} {request.url}")

    def _token(self, request: httpx.Request) -> httpx.Response:
        form = dict(parse_qsl(request.content.decode()))
        self.token_requests.append(form)
        if self.token_status != 200:
            return httpx.Response(self.token_status, json={"error": "server_error"})

        pending = self._pending.pop(form.get("code", ""), None)
        challenge = b64url(hashlib.sha256(form.get("code_verifier", "").encode()).digest())
        valid = (
            pending is not None
            and form.get("grant_type") == "authorization_code"
            and form.get("client_id") == CLIENT_ID
            and form.get("client_secret") == CLIENT_SECRET
            and form.get("redirect_uri") == self.redirect_uri
            and pending["challenge"] == challenge  # PKCE S256
        )
        if not valid:
            return httpx.Response(400, json={"error": "invalid_grant"})

        self.last_id_token = self.id_token(pending["nonce"])
        return httpx.Response(
            200,
            json={
                "id_token": self.last_id_token,
                "access_token": "access-token",
                "token_type": "Bearer",
                "expires_in": 3600,
            },
        )

    def id_token(self, nonce: str) -> str:
        now = int(time.time())
        claims: dict[str, object] = {
            "iss": ISSUER,
            "aud": CLIENT_ID,
            "sub": self.sub,
            "email": self.email,
            "email_verified": True,
            "nonce": nonce,
            "iat": now,
            "exp": now + 3600,
        }
        for name, value in self.claims.items():
            if value is None:
                claims.pop(name, None)
            else:
                claims[name] = value
        return self._sign(claims)

    def _sign(self, claims: dict) -> str:
        header = {"alg": "RS256", "kid": KID}
        match self.signer:
            case "good":
                return jwt.encode(header, claims, self.key)
            case "wrong_key":
                return jwt.encode(header, claims, self.other_key)
            case "unknown_kid":
                return jwt.encode({**header, "kid": "rotated-away"}, claims, self.key)
            case "none":
                return _compact({"alg": "none", "typ": "JWT"}, claims) + "."
            case "hs256":
                # 공개키를 HMAC 비밀키처럼 써서 서명하는 알고리즘 혼동 공격
                signing_input = _compact({"alg": "HS256", "kid": KID, "typ": "JWT"}, claims)
                secret = self.key.as_pem(private=False)
                digest = hmac.new(secret, signing_input.encode(), hashlib.sha256).digest()
                return f"{signing_input}.{b64url(digest)}"
        raise ValueError(f"알 수 없는 signer: {self.signer}")


def sign_in(client, fake: FakeGoogle) -> httpx.Response:
    """로그인 시작부터 콜백까지 한 번에 진행하고 콜백 응답을 돌려준다."""
    start = client.get("/api/v1/auth/google/login")
    code, state = fake.authorize(start.headers["location"])
    return client.get("/api/v1/auth/google/callback", params={"code": code, "state": state})
