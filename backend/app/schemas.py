"""여러 라우터가 함께 쓰는 요청·응답 검증 요소."""

from datetime import UTC, datetime
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints

UtcDatetime = Annotated[datetime, AfterValidator(lambda value: value.astimezone(UTC))]


class Strict(BaseModel):
    """스펙에 없는 필드는 모두 거부한다(source_type·jd_hash·user_id 등을 조용히 바꾸지 못하게)."""

    model_config = ConfigDict(extra="forbid")


def constrained_text(max_length: int, min_length: int = 1) -> Any:
    """앞뒤 공백을 자른 뒤 길이를 검사하는 문자열 타입."""
    return Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=min_length, max_length=max_length),
    ]
