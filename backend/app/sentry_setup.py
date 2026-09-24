from typing import Any

import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.transport import Transport

# Sentry 로 보낼 수 있는 요청 헤더. Cookie·Authorization 등은 보내지 않는다.
_ALLOWED_HEADERS = {
    "user-agent",
    "content-type",
    "content-length",
    "accept",
    "accept-language",
    "host",
    "x-request-id",
}
_REDACTED = "[redacted]"


def scrub_event(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any]:
    """이벤트를 보내기 전에 이력서·JD 원문, 세션·OAuth 값이 실릴 수 있는 곳을 모두 비운다."""
    request = event.get("request")
    if request:
        for key in ("data", "cookies", "query_string", "env"):
            request.pop(key, None)
        if isinstance(request.get("url"), str):
            request["url"] = request["url"].split("?", 1)[0].split("#", 1)[0]
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = {k: v for k, v in headers.items() if k.lower() in _ALLOWED_HEADERS}

    event.pop("user", None)
    event.pop("extra", None)
    event.pop("breadcrumbs", None)

    for exception in (event.get("exception") or {}).get("values") or []:
        # 예외 종류와 스택 위치는 남기고, 메시지와 지역 변수 값은 지운다.
        exception["value"] = _REDACTED
        for frame in (exception.get("stacktrace") or {}).get("frames") or []:
            frame.pop("vars", None)
    return event


def init_sentry(dsn: str, environment: str, *, transport: Transport | None = None) -> bool:
    """DSN 이 없으면 아무것도 하지 않는다(비활성)."""
    if not dsn:
        return False
    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size="never",
        max_breadcrumbs=0,
        traces_sample_rate=0.0,
        before_send=scrub_event,
        # 로그 메시지가 이벤트나 브레드크럼으로 새지 않게 로깅 연동을 끈다.
        integrations=[LoggingIntegration(level=None, event_level=None)],
        transport=transport,
    )
    return True
