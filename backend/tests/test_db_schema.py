import uuid
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, delete, func, inspect, select
from sqlalchemy.exc import IntegrityError

import app.models  # noqa: F401  (모델을 메타데이터에 등록한다)
from app.db import Base
from app.models import AnalysisRun, AuthSession, Experience, JobPosting, User
from tests.db_utils import alembic_config, ensure_database

EXPECTED_TABLES = {"users", "sessions", "experiences", "job_postings", "analysis_runs"}


@pytest.fixture
def migration_env(database_url):
    """스키마를 만들고 지우는 테스트는 다른 테스트에 영향이 없도록 별도 DB 에서 한다."""
    url = ensure_database(database_url, suffix="_migrations")
    config = alembic_config(url)
    command.downgrade(config, "base")
    engine = create_engine(url)
    yield config, engine
    engine.dispose()


def _tables(engine) -> set[str]:
    return set(inspect(engine).get_table_names()) - {"alembic_version"}


# ---- 마이그레이션 --------------------------------------------------------


def test_upgrade_creates_expected_tables(migration_env):
    config, engine = migration_env

    command.upgrade(config, "head")

    assert _tables(engine) == EXPECTED_TABLES


def test_downgrade_removes_all_tables(migration_env):
    config, engine = migration_env
    command.upgrade(config, "head")

    command.downgrade(config, "base")

    assert _tables(engine) == set()


def test_models_and_migrations_agree(migration_env):
    config, engine = migration_env
    command.upgrade(config, "head")

    with engine.connect() as conn:
        differences = compare_metadata(MigrationContext.configure(conn), Base.metadata)

    assert differences == []


# ---- 제약 ---------------------------------------------------------------


def _user(db, email="a@example.com", sub="google-sub-a") -> User:
    user = User(email=email, google_sub=sub)
    db.add(user)
    db.commit()
    return user


def _count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


def test_user_email_and_google_sub_are_unique(db):
    _user(db)

    for email, sub in [("a@example.com", "other-sub"), ("other@example.com", "google-sub-a")]:
        db.add(User(email=email, google_sub=sub))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_experience_defaults(db):
    user = _user(db)
    db.add(Experience(user_id=user.id, title="프로젝트", source_type="manual"))
    db.commit()

    experience = db.scalar(select(Experience))

    assert experience.version == 1
    assert experience.technologies == []
    assert experience.activities == []
    assert experience.is_confirmed is False
    assert experience.created_at.tzinfo is not None


def test_experience_source_type_is_restricted(db):
    user = _user(db)
    db.add(Experience(user_id=user.id, title="프로젝트", source_type="scraped"))

    with pytest.raises(IntegrityError):
        db.commit()


def test_job_posting_is_unique_per_user_and_jd_hash(db):
    first = _user(db)
    second = _user(db, email="b@example.com", sub="google-sub-b")

    def posting(user):
        return JobPosting(
            user_id=user.id,
            job_title="AI Engineer",
            company_name="예시",
            jd_text="jd",
            jd_hash="h1",
        )

    db.add(posting(first))
    db.commit()
    db.add(posting(second))  # 다른 사용자는 같은 JD 를 저장할 수 있다
    db.commit()
    db.add(posting(first))  # 같은 사용자의 같은 JD 는 안 된다
    with pytest.raises(IntegrityError):
        db.commit()


def test_analysis_run_type_and_status_are_restricted(db):
    user = _user(db)

    for run_type, status in [("guess", "queued"), ("jd_analysis", "done")]:
        db.add(AnalysisRun(user_id=user.id, run_type=run_type, status=status))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_session_token_hash_is_unique(db):
    user = _user(db)
    expires = datetime.now(UTC) + timedelta(days=14)
    db.add(AuthSession(user_id=user.id, token_hash="a" * 64, expires_at=expires))
    db.commit()

    db.add(AuthSession(user_id=user.id, token_hash="a" * 64, expires_at=expires))
    with pytest.raises(IntegrityError):
        db.commit()


def test_deleting_user_removes_owned_rows_and_keeps_other_users_data(db):
    def populate(user) -> None:
        posting = JobPosting(
            user_id=user.id,
            job_title="AI Engineer",
            company_name="예시",
            jd_text="jd",
            jd_hash=uuid.uuid4().hex,
        )
        db.add_all(
            [
                Experience(user_id=user.id, title="프로젝트", source_type="manual"),
                AuthSession(
                    user_id=user.id,
                    token_hash=uuid.uuid4().hex,
                    expires_at=datetime.now(UTC) + timedelta(days=14),
                ),
                posting,
            ]
        )
        db.flush()
        db.add(
            AnalysisRun(
                user_id=user.id,
                job_posting_id=posting.id,
                run_type="jd_analysis",
                status="queued",
            )
        )
        db.commit()

    leaving = _user(db)
    staying = _user(db, email="b@example.com", sub="google-sub-b")
    populate(leaving)
    populate(staying)

    db.execute(delete(User).where(User.id == leaving.id))
    db.commit()

    for model in (Experience, AuthSession, JobPosting, AnalysisRun):
        remaining = db.scalars(select(model.user_id)).all()
        assert remaining == [staying.id], f"{model.__tablename__} 에 남은 행이 잘못됐다"
    assert _count(db, User) == 1
