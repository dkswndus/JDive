"""계정 삭제(`DELETE /me`): 사용자 소유 데이터와 세션은 지우고, 다른 사용자의 데이터는 남긴다."""

import uuid

import pytest
from sqlalchemy import func, select

from app.models import AnalysisRun, AuthSession, Experience, JobPosting, User
from tests.fake_google import ORIGIN, sign_in

ME = "/api/v1/me"
OWNED_MODELS = (Experience, JobPosting, AnalysisRun, AuthSession)


def add_owned_data(db, user_id) -> None:
    """사용자 한 명 몫의 경험·공고·분석 기록을 넣는다(세션은 로그인으로 생긴다)."""
    posting = JobPosting(
        user_id=user_id,
        job_title="AI Engineer",
        company_name="예시",
        jd_text="가상의 JD",
        jd_hash=uuid.uuid4().hex,
    )
    db.add_all(
        [Experience(user_id=user_id, title="가상의 프로젝트", source_type="manual"), posting]
    )
    db.flush()
    db.add(
        AnalysisRun(
            user_id=user_id, job_posting_id=posting.id, run_type="jd_analysis", status="queued"
        )
    )
    db.commit()


def owner_ids(db, model) -> list[uuid.UUID]:
    return db.scalars(select(model.user_id)).all()


def user_count(db) -> int:
    return db.scalar(select(func.count()).select_from(User))


@pytest.fixture
def two_users(make_auth_client, fake_google, db):
    """로그인한 두 사용자와 각자의 데이터. (떠날 사람 클라이언트, 남을 사람 클라이언트, 두 ID)"""
    leaving, staying = make_auth_client(), make_auth_client()
    sign_in(leaving, fake_google)
    fake_google.sub, fake_google.email = "google-sub-2", "staying@example.com"
    sign_in(staying, fake_google)
    by_email = {user.email: user.id for user in db.scalars(select(User))}
    leaving_id, staying_id = by_email["user@example.com"], by_email["staying@example.com"]
    add_owned_data(db, leaving_id)
    add_owned_data(db, staying_id)
    return leaving, staying, leaving_id, staying_id


def test_delete_me_removes_the_user_and_everything_they_own(two_users, db):
    leaving, _, leaving_id, _ = two_users

    response = leaving.delete(ME, headers={"Origin": ORIGIN})

    assert response.status_code == 204
    assert db.get(User, leaving_id) is None
    for model in OWNED_MODELS:
        assert leaving_id not in owner_ids(db, model), f"{model.__tablename__} 에 남아 있다"


def test_delete_me_keeps_other_users_data_and_sessions(two_users, db):
    leaving, staying, _, staying_id = two_users

    leaving.delete(ME, headers={"Origin": ORIGIN})

    for model in OWNED_MODELS:
        assert owner_ids(db, model) == [staying_id], f"{model.__tablename__} 이 달라졌다"
    assert user_count(db) == 1
    assert staying.get(ME).status_code == 200


def test_delete_me_ends_the_session_and_clears_the_cookie(two_users):
    leaving, *_ = two_users

    leaving.delete(ME, headers={"Origin": ORIGIN})

    assert leaving.cookies.get("jdive_session") is None
    assert leaving.get(ME).status_code == 401


def test_delete_me_ends_every_session_of_the_user(make_auth_client, fake_google, db):
    first, second = make_auth_client(), make_auth_client()  # 같은 사용자의 두 기기
    sign_in(first, fake_google)
    sign_in(second, fake_google)

    first.delete(ME, headers={"Origin": ORIGIN})

    assert second.get(ME).status_code == 401
    assert db.scalar(select(func.count()).select_from(AuthSession)) == 0


def test_delete_me_requires_a_session(auth_client):
    assert auth_client.delete(ME, headers={"Origin": ORIGIN}).status_code == 401


def test_delete_me_from_a_foreign_or_missing_origin_deletes_nothing(auth_client, fake_google, db):
    sign_in(auth_client, fake_google)

    foreign = auth_client.delete(ME, headers={"Origin": "http://evil.example.com"})
    missing = auth_client.delete(ME)

    for response in (foreign, missing):
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "csrf_origin_mismatch"
    assert user_count(db) == 1
    assert auth_client.get(ME).status_code == 200


def test_signing_in_again_after_deletion_starts_from_an_empty_account(auth_client, fake_google, db):
    sign_in(auth_client, fake_google)
    old_id = db.scalar(select(User.id))
    add_owned_data(db, old_id)
    auth_client.delete(ME, headers={"Origin": ORIGIN})

    sign_in(auth_client, fake_google)

    new_id = db.scalar(select(User.id))
    assert new_id != old_id
    assert db.scalar(select(func.count()).select_from(Experience)) == 0
    assert db.scalar(select(func.count()).select_from(JobPosting)) == 0
