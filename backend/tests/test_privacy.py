import json
import logging
from pathlib import Path

import pytest
import sentry_sdk
from sentry_sdk.transport import Transport

from app.sentry_setup import init_sentry, scrub_event
from tests.conftest import SENTINEL

SENTINEL_COOKIE = "SENTINEL-COOKIE-51d2"
SENTINEL_CODE = "SENTINEL-CODE-77aa"
SENTINEL_TOKEN = "SENTINEL-TOKEN-0be1"
ALL_SENTINELS = [SENTINEL, SENTINEL_COOKIE, SENTINEL_CODE, SENTINEL_TOKEN]


class CaptureTransport(Transport):
    """Sentry 로 나가는 이벤트를 네트워크 대신 메모리에 모은다."""

    def __init__(self, options=None):
        super().__init__(options)
        self.events: list[dict] = []

    def capture_envelope(self, envelope):
        event = envelope.get_event()
        if event is not None:
            self.events.append(event)


@pytest.fixture
def sentry_events():
    transport = CaptureTransport()
    init_sentry("https://public@example.invalid/1", "test", transport=transport)
    yield transport.events
    sentry_sdk.get_client().close()
    sentry_sdk.init()  # 다른 테스트에 영향이 없도록 비활성 상태로 되돌린다


# ---- 서버 로그 ----------------------------------------------------------


def test_request_body_never_appears_in_logs(client, caplog):
    with caplog.at_level(logging.DEBUG):
        client.post("/_t/validate", json={"jd_text": SENTINEL * 3})

    assert SENTINEL not in caplog.text


def test_unhandled_exception_logs_type_and_location_but_not_message(client, caplog):
    with caplog.at_level(logging.DEBUG):
        client.post(
            "/_t/boom-body",
            json={"jd_text": SENTINEL},
            headers={"Cookie": f"jdive_session={SENTINEL_COOKIE}"},
        )

    assert "unhandled_exception" in caplog.text
    assert "RuntimeError" in caplog.text
    for secret in (SENTINEL, SENTINEL_COOKIE):
        assert secret not in caplog.text


def test_uvicorn_access_log_is_disabled_because_it_prints_query_strings(client):
    assert logging.getLogger("uvicorn.access").disabled is True


def test_dockerfile_starts_uvicorn_without_access_log():
    dockerfile = (Path(__file__).parents[1] / "Dockerfile").read_text(encoding="utf-8")

    assert "--no-access-log" in dockerfile


# ---- Sentry (백엔드) ----------------------------------------------------


def test_init_without_dsn_is_disabled():
    assert init_sentry("", "test") is False
    assert sentry_sdk.get_client().is_active() is False


def test_init_disables_pii_locals_body_and_breadcrumbs(sentry_events):
    options = sentry_sdk.get_client().options

    assert options["send_default_pii"] is False
    assert options["include_local_variables"] is False
    assert options["max_request_body_size"] == "never"
    assert options["max_breadcrumbs"] == 0


def test_unhandled_exception_is_reported_without_original_text(sentry_events, client):
    client.post(
        "/_t/boom-body?code=" + SENTINEL_CODE,
        json={"jd_text": SENTINEL},
        headers={
            "Cookie": f"jdive_session={SENTINEL_COOKIE}",
            "Authorization": f"Bearer {SENTINEL_TOKEN}",
        },
    )

    assert sentry_events, "예외가 Sentry 로 보고되지 않았다 (테스트가 아무것도 증명하지 못한다)"
    assert len(sentry_events) == 1, "같은 예외가 중복 보고됐다"
    serialized = json.dumps(sentry_events, ensure_ascii=False)
    for secret in ALL_SENTINELS:
        assert secret not in serialized
    assert "RuntimeError" in serialized  # 예외 종류와 위치는 남겨야 디버깅할 수 있다


def test_scrub_event_removes_request_user_locals_and_breadcrumbs():
    event = {
        "request": {
            "url": "http://localhost:3000/api/v1/experiences",
            "method": "POST",
            "query_string": f"code={SENTINEL_CODE}",
            "cookies": {"jdive_session": SENTINEL_COOKIE},
            "data": {"jd_text": SENTINEL},
            "headers": {
                "Authorization": f"Bearer {SENTINEL_TOKEN}",
                "Cookie": f"jdive_session={SENTINEL_COOKIE}",
                "User-Agent": "pytest",
                "X-Request-ID": "req_1",
            },
        },
        "user": {"email": "person@example.com", "id": "u1"},
        "extra": {"jd_text": SENTINEL},
        "breadcrumbs": {"values": [{"message": SENTINEL, "data": {"jd_text": SENTINEL}}]},
        "exception": {
            "values": [
                {
                    "type": "RuntimeError",
                    "value": f"처리 실패: {SENTINEL}",
                    "stacktrace": {"frames": [{"function": "boom", "vars": {"jd_text": SENTINEL}}]},
                }
            ]
        },
    }

    scrubbed = scrub_event(event, {})

    serialized = json.dumps(scrubbed, ensure_ascii=False)
    for secret in [*ALL_SENTINELS, "person@example.com"]:
        assert secret not in serialized
    assert scrubbed["exception"]["values"][0]["type"] == "RuntimeError"
    assert scrubbed["request"]["headers"] == {"User-Agent": "pytest", "X-Request-ID": "req_1"}
    assert scrubbed["request"]["method"] == "POST"
