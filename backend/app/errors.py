from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.logging_config import request_id_var

_STATUS_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
}

# HTTPException.detail 은 임의 문자열일 수 있어 쓰지 않고, 상태 코드별 고정 문구만 내보낸다.
_STATUS_MESSAGES = {
    400: "잘못된 요청입니다.",
    401: "로그인이 필요합니다.",
    403: "요청을 처리할 수 없습니다.",
    404: "찾을 수 없습니다.",
    405: "허용되지 않는 요청입니다.",
    409: "요청이 현재 상태와 충돌합니다.",
    422: "입력값을 확인해 주세요.",
    429: "요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.",
}


class AppError(Exception):
    """API 가 의도적으로 돌려주는 오류. 응답은 {"error": {...}} 형식이다."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        details: list[dict[str, Any]] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or []
        self.extra = extra or {}


def error_body(
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {
        "code": code,
        "message": message,
        "details": details or [],
        "request_id": request_id_var.get(),
    }
    if extra:
        error.update(extra)
    return {"error": error}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        body = error_body(exc.code, exc.message, exc.details, exc.extra)
        return JSONResponse(body, status_code=exc.status_code)

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _STATUS_CODES.get(exc.status_code, "http_error")
        message = _STATUS_MESSAGES.get(exc.status_code, "요청을 처리하지 못했습니다.")
        return JSONResponse(
            error_body(code, message), status_code=exc.status_code, headers=exc.headers
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # 입력값(input)은 응답에 되돌려 보내지 않는다. 어느 필드가 어떤 이유로 틀렸는지만 알린다.
        details = [
            {
                "field": ".".join(str(part) for part in err["loc"][1:]) or "body",
                "issue": err["type"],
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            error_body("validation_error", _STATUS_MESSAGES[422], details), status_code=422
        )
