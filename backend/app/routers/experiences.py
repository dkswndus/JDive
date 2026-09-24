"""경험 CRUD(1단계: 수동 등록). 스펙 §4.3.1."""

import secrets
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import get_db
from app.errors import AppError
from app.models import Experience, User

router = APIRouter(prefix="/experiences")

UserDep = Annotated[User, Depends(get_current_user)]
DbDep = Annotated[Session, Depends(get_db)]

INVALID_INPUT = "입력값을 확인해 주세요."


def _text(max_length: int) -> Any:
    return Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=max_length)
    ]


Title = _text(100)
Technology = _text(40)  # experiences.technologies 는 varchar(40)[] 다
ActivityText = _text(500)
Technologies = Annotated[list[Technology], Field(max_length=30)]
UtcDatetime = Annotated[datetime, AfterValidator(lambda value: value.astimezone(UTC))]


class Strict(BaseModel):
    """스펙에 없는 필드는 모두 거부한다(source_type·version 등을 조용히 바꾸지 못하게)."""

    model_config = ConfigDict(extra="forbid")


class ActivityCreate(Strict):
    text: ActivityText


class ActivityUpdate(Strict):
    """`source_span` 은 읽기 전용이라 받아도 무시한다(GET 응답을 그대로 돌려보내도 되도록)."""

    id: str | None = None  # 기존 항목이면 ID 를 함께 보낸다. 없으면 새 항목이다.
    text: ActivityText
    source_span: str | None = Field(default=None, exclude=True)


class ExperienceCreate(Strict):
    title: Title
    role: Title | None = None
    technologies: Technologies = Field(default_factory=list)
    activities: Annotated[list[ActivityCreate], Field(min_length=1, max_length=20)]
    source_type: Literal["manual"] = "manual"  # 1단계는 수동 등록만 받는다


class ExperiencePatch(Strict):
    title: Title | None = None
    role: Title | None = None  # null 로 보내면 지운다
    technologies: Technologies | None = None
    activities: Annotated[list[ActivityUpdate], Field(min_length=1, max_length=20)] | None = None

    @model_validator(mode="after")
    def _at_least_one_and_no_null_where_required(self) -> "ExperiencePatch":
        if not self.model_fields_set:
            raise ValueError("no fields")
        for name in ("title", "technologies", "activities"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class ActivityOut(BaseModel):
    id: str
    text: str
    source_span: str | None = None


class ExperienceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    role: str | None
    technologies: list[str]
    activities: list[ActivityOut]
    source_type: str
    is_confirmed: bool
    confirmed_at: UtcDatetime | None
    version: int
    created_at: UtcDatetime
    updated_at: UtcDatetime


class ExperienceList(BaseModel):
    items: list[ExperienceOut]


def _new_activity(text: str) -> dict[str, Any]:
    # 무작위(8자리 16진수)라 항목을 지우고 새로 추가해도 이전 ID 가 재사용되지 않는다.
    # 한 경험 안에서 충돌할 확률은 무시할 만하다.
    return {"id": f"a{secrets.token_hex(4)}", "text": text, "source_span": None}


def _merge_activities(items: list[ActivityUpdate], stored: list[dict[str, Any]]) -> list[dict]:
    known = {activity["id"]: activity for activity in stored}
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if item.id is None:
            merged.append(_new_activity(item.text))
            continue
        if item.id not in known or item.id in seen:
            issue = "duplicate_id" if item.id in seen else "unknown_id"
            details = [{"field": f"activities.{index}.id", "issue": issue}]
            raise AppError(422, "validation_error", INVALID_INPUT, details=details)
        seen.add(item.id)
        merged.append({**known[item.id], "text": item.text})  # source_span 은 저장된 값을 유지한다
    return merged


def _get_owned(db: Session, user: User, experience_id: uuid.UUID) -> Experience:
    experience = db.scalar(
        select(Experience).where(Experience.id == experience_id, Experience.user_id == user.id)
    )
    if experience is None:  # 없는 경우와 타인 소유인 경우를 구분하지 않는다
        raise AppError(404, "not_found", "경험을 찾을 수 없습니다.")
    return experience


@router.post("", status_code=201)
def create_experience(body: ExperienceCreate, user: UserDep, db: DbDep) -> ExperienceOut:
    experience = Experience(
        user_id=user.id,
        title=body.title,
        role=body.role,
        technologies=body.technologies,
        activities=[_new_activity(activity.text) for activity in body.activities],
        source_type=body.source_type,
        is_confirmed=True,
        confirmed_at=datetime.now(UTC),
    )
    db.add(experience)
    db.commit()
    return ExperienceOut.model_validate(experience)


@router.get("")
def list_experiences(user: UserDep, db: DbDep) -> ExperienceList:
    # ponytail: 페이지네이션 없이 모두 돌려준다. 한 사용자의 경험은 많아야 수십 개다.
    rows = db.scalars(
        select(Experience)
        .where(Experience.user_id == user.id)
        .order_by(Experience.created_at, Experience.id)
    )
    return ExperienceList(items=[ExperienceOut.model_validate(row) for row in rows])


@router.get("/{experience_id}")
def get_experience(experience_id: uuid.UUID, user: UserDep, db: DbDep) -> ExperienceOut:
    return ExperienceOut.model_validate(_get_owned(db, user, experience_id))


@router.patch("/{experience_id}")
def update_experience(
    experience_id: uuid.UUID, body: ExperiencePatch, user: UserDep, db: DbDep
) -> ExperienceOut:
    experience = _get_owned(db, user, experience_id)
    requested: dict[str, Any] = {}
    for name in ("title", "role", "technologies"):
        if name in body.model_fields_set:
            requested[name] = getattr(body, name)
    if body.activities is not None:
        requested["activities"] = _merge_activities(body.activities, experience.activities)

    changes = {k: v for k, v in requested.items() if getattr(experience, k) != v}
    if changes:  # 값이 실제로 바뀐 경우에만 version 을 올린다(R5)
        for name, value in changes.items():
            setattr(experience, name, value)
        experience.version += 1
        db.commit()  # 서버가 채우는 updated_at 은 SQLAlchemy 가 만료시켜 다시 읽는다
    return ExperienceOut.model_validate(experience)


@router.delete("/{experience_id}", status_code=204)
def delete_experience(experience_id: uuid.UUID, user: UserDep, db: DbDep) -> Response:
    db.delete(_get_owned(db, user, experience_id))
    db.commit()
    return Response(status_code=204)
