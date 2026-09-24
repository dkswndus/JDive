import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )


def _owner() -> Mapped[uuid.UUID]:
    """사용자 소유 행. 사용자가 삭제되면 DB 가 함께 지운다(계정 삭제)."""
    return mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    google_sub: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_at: Mapped[datetime] = _created_at()


class AuthSession(Base):
    """로그인 세션. 쿠키의 토큰이 아니라 그 SHA-256 해시만 저장한다."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _owner()
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = _created_at()
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Experience(Base):
    __tablename__ = "experiences"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('resume_extract', 'manual', 'supplement')",
            name="ck_experiences_source_type",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _owner()
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str | None] = mapped_column(String(100))
    technologies: Mapped[list[str]] = mapped_column(
        ARRAY(String(40)), server_default=text("'{}'"), nullable=False
    )
    # [{"id": "...", "text": "...", "source_span": "..."}]
    activities: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    is_confirmed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1"), nullable=False
    )
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class JobPosting(Base):
    __tablename__ = "job_postings"
    __table_args__ = (UniqueConstraint("user_id", "jd_hash", name="uq_job_postings_user_jd_hash"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _owner()
    job_title: Mapped[str] = mapped_column(String(150), nullable=False)
    company_name: Mapped[str] = mapped_column(String(100), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2000))
    jd_text: Mapped[str] = mapped_column(Text, nullable=False)
    jd_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = _created_at()


class AnalysisRun(Base):
    """AI 호출 한 번의 기록. 1단계에서는 테이블만 만들고 쓰지 않는다."""

    __tablename__ = "analysis_runs"
    __table_args__ = (
        CheckConstraint(
            "run_type IN ('experience_extraction', 'jd_analysis')",
            name="ck_analysis_runs_run_type",
        ),
        CheckConstraint(
            "status IN ('queued', 'extracting_requirements', 'matching', 'completed', 'failed')",
            name="ck_analysis_runs_status",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = _owner()
    job_posting_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("job_postings.id", ondelete="CASCADE"), index=True
    )
    run_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), default="queued", server_default="queued", nullable=False
    )
    stage: Mapped[str | None] = mapped_column(String(30))
    model_version: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(100))
    schema_version: Mapped[str | None] = mapped_column(String(50))
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    attempt_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    error_class: Mapped[str | None] = mapped_column(String(50))
    token_usage: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    input_experience_versions: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    validation_stats: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
