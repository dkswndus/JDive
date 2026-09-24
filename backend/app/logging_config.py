import contextvars
import json
import logging
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)

# 로그에 남길 수 있는 추가 필드. 이 목록 밖의 값(요청 본문, 쿼리 문자열 등)은 기록하지 않는다.
_ALLOWED_EXTRA = ("method", "path", "status", "duration_ms", "exc_type", "where")
_MAX_FRAMES = 8


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "request_id", None):
            record.request_id = request_id_var.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None) or request_id_var.get(),
        }
        for key in _ALLOWED_EXTRA:
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        # exc_info 는 일부러 기록하지 않는다. 예외 메시지에 사용자 입력이 섞일 수 있다.
        return json.dumps(payload, ensure_ascii=False)


def describe_exception(exc: BaseException) -> tuple[str, str]:
    """예외 종류와 발생 위치(파일:줄:함수)만 돌려준다. 메시지는 사용자 입력을 담을 수 있어 뺀다."""
    frames = traceback.extract_tb(exc.__traceback__)[-_MAX_FRAMES:]  # 가장 안쪽 프레임만
    where = " <- ".join(f"{Path(f.filename).name}:{f.lineno}:{f.name}" for f in reversed(frames))
    return type(exc).__name__, where


_handler: logging.Handler | None = None


def configure_logging(level: int = logging.INFO) -> None:
    """루트 로거에 JSON 핸들러를 한 번만 붙인다."""
    global _handler
    root = logging.getLogger()
    if _handler is None:
        _handler = logging.StreamHandler(sys.stdout)
        _handler.setFormatter(JsonFormatter())
        _handler.addFilter(RequestIdFilter())
    if _handler not in root.handlers:
        root.addHandler(_handler)
    root.setLevel(level)
    # httpx 는 요청 URL 을 남기고, uvicorn 접속 로그는 쿼리 문자열(OAuth code·state)을 남긴다.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").disabled = True
