import logging
import re
import time
import uuid

import sentry_sdk
from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.errors import error_body
from app.logging_config import describe_exception, request_id_var

_REQUEST_ID_RE = re.compile(r"[A-Za-z0-9._-]{8,64}")
access_logger = logging.getLogger("jdive.access")
app_logger = logging.getLogger("jdive.app")


class RequestContextMiddleware:
    """요청마다 X-Request-ID 를 정하고, 접속 로그를 남기고, 처리되지 않은 예외를 500 으로 바꾼다.

    접속 로그에는 메서드·경로·상태·소요 시간만 남긴다. 쿼리 문자열(OAuth code·state)과
    요청 본문(이력서·JD 원문)은 기록하지 않는다.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = self._resolve_request_id(scope)
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        status = 500
        response_started = False

        async def send_with_request_id(message: Message) -> None:
            nonlocal status, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status = message["status"]
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        try:
            try:
                await self.app(scope, receive, send_with_request_id)
            except Exception as exc:
                exc_type, where = describe_exception(exc)
                app_logger.error(
                    "unhandled_exception type=%s",
                    exc_type,
                    extra={"exc_type": exc_type, "where": where},
                )
                # 예외를 여기서 500 응답으로 바꾸므로 Sentry 최외곽 미들웨어까지 닿지 않는다.
                # 그래서 직접 보고한다. 로깅 연동은 꺼 두었으니 위 로그가 중복 이벤트가 되지 않는다.
                sentry_sdk.capture_exception(exc)
                if response_started:
                    raise
                response = JSONResponse(
                    error_body("internal_error", "서버에서 오류가 발생했습니다."), status_code=500
                )
                await response(scope, receive, send_with_request_id)
        finally:
            access_logger.info(
                "request",
                extra={
                    "request_id": request_id,
                    "method": scope["method"],
                    "path": scope["path"],
                    "status": status,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
            request_id_var.reset(token)

    @staticmethod
    def _resolve_request_id(scope: Scope) -> str:
        for name, value in scope["headers"]:
            if name == b"x-request-id":
                candidate = value.decode("latin-1")
                if _REQUEST_ID_RE.fullmatch(candidate):
                    return candidate
                break
        return f"req_{uuid.uuid4().hex}"
