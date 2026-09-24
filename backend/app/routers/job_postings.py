"""공고 저장·중복 감지·조회(1단계). 스펙 §4.4.1."""

import hashlib
import unicodedata
import uuid
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends
from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, defer

from app.auth import get_current_user
from app.db import get_db
from app.errors import AppError
from app.models import JobPosting, User
from app.schemas import Strict, UtcDatetime, constrained_text

router = APIRouter(prefix="/job-postings")

UserDep = Annotated[User, Depends(get_current_user)]
DbDep = Annotated[Session, Depends(get_db)]

WEB_SCHEMES = {"http", "https"}


def _web_url(value: str) -> str | None:
    """빈 값은 저장하지 않고, 있으면 http·https 주소만 받는다(javascript: 등 차단)."""
    if not value:
        return None
    parts = urlsplit(value)
    has_whitespace = any(char.isspace() or ord(char) < 32 for char in value)
    if parts.scheme.lower() not in WEB_SCHEMES or not parts.hostname or has_whitespace:
        raise ValueError("not a web address")
    return value


SourceUrl = (
    Annotated[
        str, StringConstraints(strip_whitespace=True, max_length=2000), AfterValidator(_web_url)
    ]
    | None
)


class PostingCreate(Strict):
    job_title: constrained_text(150)
    company_name: constrained_text(100)
    source_url: SourceUrl = None
    jd_text: constrained_text(15000, min_length=200)


class PostingSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_title: str
    company_name: str
    source_url: str | None
    created_at: UtcDatetime


class PostingOut(PostingSummary):
    jd_text: str


class PostingList(BaseModel):
    items: list[PostingSummary]


def jd_hash(text: str) -> str:
    """NFC 로 맞추고 모든 공백 연속을 하나로 줄인 뒤 SHA-256 한다.

    줄바꿈이나 공백만 다른 복사본이 새 JD 로 저장되지 않게 한다.
    """
    normalized = " ".join(unicodedata.normalize("NFC", text).split())
    return hashlib.sha256(normalized.encode()).hexdigest()


@router.post("", status_code=201)
def create_posting(body: PostingCreate, user: UserDep, db: DbDep) -> PostingOut:
    user_id, digest = user.id, jd_hash(body.jd_text)
    posting = JobPosting(
        user_id=user_id,
        job_title=body.job_title,
        company_name=body.company_name,
        source_url=body.source_url,
        jd_text=body.jd_text,
        jd_hash=digest,
    )
    db.add(posting)
    try:
        db.commit()
    except IntegrityError:
        # 미리 조회하지 않고 유니크 제약에 맡긴다. 동시에 같은 JD 를 저장해도 하나만 남는다.
        db.rollback()
        existing_id = db.scalar(
            select(JobPosting.id).where(JobPosting.user_id == user_id, JobPosting.jd_hash == digest)
        )
        if existing_id is None:
            raise
        raise AppError(
            409,
            "duplicate_posting",
            "이미 저장한 공고입니다.",
            extra={"existing_posting_id": str(existing_id)},
        ) from None
    return PostingOut.model_validate(posting)


@router.get("")
def list_postings(user: UserDep, db: DbDep) -> PostingList:
    # ponytail: 페이지네이션 없이 모두 돌려준다. 목록에는 큰 jd_text 를 읽지 않는다.
    rows = db.scalars(
        select(JobPosting)
        .options(defer(JobPosting.jd_text))
        .where(JobPosting.user_id == user.id)
        .order_by(JobPosting.created_at.desc(), JobPosting.id)
    )
    return PostingList(items=[PostingSummary.model_validate(row) for row in rows])


@router.get("/{posting_id}")
def get_posting(posting_id: uuid.UUID, user: UserDep, db: DbDep) -> PostingOut:
    posting = db.scalar(
        select(JobPosting).where(JobPosting.id == posting_id, JobPosting.user_id == user.id)
    )
    if posting is None:  # 없는 경우와 타인 소유인 경우를 구분하지 않는다
        raise AppError(404, "not_found", "공고를 찾을 수 없습니다.")
    return PostingOut.model_validate(posting)
