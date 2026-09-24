"""경험 CRUD(1단계: 수동 등록). 소유권, 검증, 수정 시 version 규칙, 원문 비노출."""

import logging
import re
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Experience, User
from tests.conftest import SENTINEL
from tests.fake_google import ORIGIN, sign_in

EXPERIENCES = "/api/v1/experiences"
HEADERS = {"Origin": ORIGIN}
ACTIVITY_ID = re.compile(r"^a[0-9a-f]{8}$")


def card(**overrides) -> dict:
    body = {
        "title": "가상의 프로젝트",
        "role": "백엔드 개발",
        "technologies": ["Python", "FastAPI"],
        "activities": [{"text": "API 서버를 구현했다"}, {"text": "배포 파이프라인을 만들었다"}],
    }
    return {**body, **overrides}


@pytest.fixture
def client(auth_client, fake_google):
    sign_in(auth_client, fake_google)
    return auth_client


@pytest.fixture
def other_user(make_auth_client, fake_google, client, db):
    """`client` 와 다른 사용자로 로그인한 클라이언트. 두 사용자가 같은 DB 를 쓴다."""
    fake_google.sub, fake_google.email = "google-sub-2", "other@example.com"
    other = make_auth_client()
    sign_in(other, fake_google)
    return other


def create(client, **overrides) -> dict:
    response = client.post(EXPERIENCES, json=card(**overrides), headers=HEADERS)
    assert response.status_code == 201, response.text
    return response.json()


def count(db) -> int:
    return db.scalar(select(func.count()).select_from(Experience))


# ---- 등록 --------------------------------------------------------------------


def test_create_returns_the_saved_experience_with_server_fields(client, db):
    response = client.post(EXPERIENCES, json=card(), headers=HEADERS)

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "가상의 프로젝트"
    assert body["role"] == "백엔드 개발"
    assert body["technologies"] == ["Python", "FastAPI"]
    assert body["source_type"] == "manual"
    assert body["is_confirmed"] is True
    assert body["confirmed_at"] is not None
    assert body["version"] == 1
    assert body["created_at"] and body["updated_at"]
    assert "user_id" not in body
    ids = [activity["id"] for activity in body["activities"]]
    assert all(ACTIVITY_ID.match(activity_id) for activity_id in ids)
    assert len(set(ids)) == 2
    assert [a["text"] for a in body["activities"]] == [
        "API 서버를 구현했다",
        "배포 파이프라인을 만들었다",
    ]
    assert all(activity["source_span"] is None for activity in body["activities"])

    saved = db.scalar(select(Experience))
    assert saved.user_id == db.scalar(select(User.id))
    assert str(saved.id) == body["id"]


def test_create_needs_only_a_title_and_one_activity(client):
    response = client.post(
        EXPERIENCES, json={"title": "최소 입력", "activities": [{"text": "한 줄"}]}, headers=HEADERS
    )

    assert response.status_code == 201
    assert response.json()["role"] is None
    assert response.json()["technologies"] == []


def test_create_trims_surrounding_whitespace(client):
    body = create(
        client,
        title="  프로젝트  ",
        role=" 개발 ",
        technologies=[" Python "],
        activities=[{"text": "  내용  "}],
    )

    assert (body["title"], body["role"], body["technologies"]) == ("프로젝트", "개발", ["Python"])
    assert body["activities"][0]["text"] == "내용"


INVALID_CARDS = [
    pytest.param({"title": None}, "title", id="no-title"),
    pytest.param({"title": "   "}, "title", id="blank-title"),
    pytest.param({"title": "가" * 101}, "title", id="title-too-long"),
    pytest.param({"role": "가" * 101}, "role", id="role-too-long"),
    pytest.param({"technologies": [f"t{i}" for i in range(31)]}, "technologies", id="31-techs"),
    pytest.param({"technologies": ["x" * 41]}, "technologies.0", id="tech-too-long"),
    pytest.param({"technologies": ["  "]}, "technologies.0", id="blank-tech"),
    pytest.param({"activities": []}, "activities", id="no-activities"),
    pytest.param({"activities": None}, "activities", id="activities-missing"),
    pytest.param({"activities": [{"text": "  "}]}, "activities.0.text", id="blank-activity"),
    pytest.param({"activities": [{"text": "가" * 501}]}, "activities.0.text", id="activity-long"),
    pytest.param({"activities": [{"text": "x"}] * 51}, "activities", id="51-activities"),
    pytest.param(
        {"activities": [{"text": "x", "source_span": "AI"}]}, "activities.0.source_span", id="span"
    ),
    pytest.param({"source_type": "resume_extract"}, "source_type", id="not-manual"),
    pytest.param({"extraction_run_id": str(uuid.uuid4())}, "extraction_run_id", id="run-id"),
    pytest.param({"is_confirmed": False}, "is_confirmed", id="unknown-field"),
]


@pytest.mark.parametrize(("overrides", "field"), INVALID_CARDS)
def test_create_rejects_invalid_input(client, db, overrides, field):
    body = {k: v for k, v in card(**overrides).items() if v is not None}

    response = client.post(EXPERIENCES, json=body, headers=HEADERS)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert field in [detail["field"] for detail in error["details"]]
    assert count(db) == 0


def test_validation_errors_do_not_echo_the_input(client):
    response = client.post(
        EXPERIENCES,
        json=card(title=SENTINEL * 20, activities=[{"text": SENTINEL * 100}]),
        headers=HEADERS,
    )

    assert response.status_code == 422
    assert SENTINEL not in response.text


def test_experience_text_never_appears_in_logs(client, caplog):
    caplog.set_level(logging.DEBUG)
    created = create(client, title=SENTINEL, activities=[{"text": SENTINEL}])
    client.patch(f"{EXPERIENCES}/{created['id']}", json={"role": SENTINEL}, headers=HEADERS)
    client.post(EXPERIENCES, json=card(title=SENTINEL * 20), headers=HEADERS)  # 422

    assert SENTINEL not in caplog.text + "".join(str(vars(r)) for r in caplog.records)


# ---- 조회 --------------------------------------------------------------------


def test_list_is_empty_at_first(client):
    response = client.get(EXPERIENCES)

    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_list_returns_only_own_experiences_in_creation_order(client, other_user):
    first = create(client, title="첫 번째")
    second = create(client, title="두 번째")
    other_user.post(EXPERIENCES, json=card(title="남의 것"), headers=HEADERS)

    items = client.get(EXPERIENCES).json()["items"]

    assert [item["id"] for item in items] == [first["id"], second["id"]]
    assert other_user.get(EXPERIENCES).json()["items"][0]["title"] == "남의 것"


def test_get_returns_own_experience(client):
    created = create(client)

    response = client.get(f"{EXPERIENCES}/{created['id']}")

    assert response.status_code == 200
    assert response.json() == created


def test_experiences_are_still_there_after_signing_in_again(client, make_auth_client, fake_google):
    created = create(client)
    fake_google.sub, fake_google.email = "google-sub-1", "user@example.com"

    returning = make_auth_client()  # 다른 기기·새 세션
    sign_in(returning, fake_google)

    assert [i["id"] for i in returning.get(EXPERIENCES).json()["items"]] == [created["id"]]


def test_get_returns_404_for_missing_and_for_other_users(client, other_user):
    theirs = create(other_user, title="남의 것")

    for experience_id in (theirs["id"], str(uuid.uuid4())):
        response = client.get(f"{EXPERIENCES}/{experience_id}")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"


def test_get_rejects_a_malformed_id(client):
    assert client.get(f"{EXPERIENCES}/not-a-uuid").status_code == 422


# ---- 수정 --------------------------------------------------------------------


def test_patch_changes_fields_and_bumps_version(client):
    created = create(client)

    response = client.patch(
        f"{EXPERIENCES}/{created['id']}",
        json={"title": "바뀐 제목", "technologies": ["Go"]},
        headers=HEADERS,
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["title"], body["technologies"]) == ("바뀐 제목", ["Go"])
    assert body["role"] == "백엔드 개발"  # 보내지 않은 필드는 그대로다
    assert body["version"] == 2
    assert body["updated_at"] > created["updated_at"]
    assert body["created_at"] == created["created_at"]
    assert client.get(f"{EXPERIENCES}/{created['id']}").json() == body


def test_each_change_bumps_version_by_one(client):
    created = create(client)
    url = f"{EXPERIENCES}/{created['id']}"

    client.patch(url, json={"title": "둘"}, headers=HEADERS)
    response = client.patch(url, json={"title": "셋"}, headers=HEADERS)

    assert response.json()["version"] == 3


def test_patch_with_the_same_values_changes_nothing(client):
    created = create(client)

    response = client.patch(
        f"{EXPERIENCES}/{created['id']}",
        json={"title": created["title"], "activities": created["activities"]},
        headers=HEADERS,
    )

    assert response.status_code == 200
    assert response.json() == created  # version·updated_at 그대로


def test_patch_null_role_clears_it_but_null_title_is_rejected(client):
    created = create(client)
    url = f"{EXPERIENCES}/{created['id']}"

    assert client.patch(url, json={"role": None}, headers=HEADERS).json()["role"] is None
    assert client.patch(url, json={"title": None}, headers=HEADERS).status_code == 422


def test_patch_activities_keeps_ids_and_source_span_of_existing_items(client, db):
    user_id = db.scalar(select(User.id))
    stored = Experience(
        user_id=user_id,
        title="AI 가 만든 경험",
        source_type="resume_extract",
        activities=[
            {"id": "a1111111", "text": "예전 내용", "source_span": "원문 일부"},
            {"id": "a2222222", "text": "지울 내용", "source_span": "다른 원문"},
        ],
    )
    db.add(stored)
    db.commit()

    response = client.patch(
        f"{EXPERIENCES}/{stored.id}",
        json={
            "activities": [
                {"text": "새 항목"},
                # source_span 은 읽기 전용이라, 보내도 저장된 값이 유지된다.
                {"id": "a1111111", "text": "고친 내용", "source_span": "위조한 원문"},
            ]
        },
        headers=HEADERS,
    )

    activities = response.json()["activities"]
    assert response.status_code == 200
    assert [a["text"] for a in activities] == ["새 항목", "고친 내용"]  # 요청한 순서를 따른다
    assert ACTIVITY_ID.match(activities[0]["id"])
    assert activities[0]["source_span"] is None
    assert activities[1] == {"id": "a1111111", "text": "고친 내용", "source_span": "원문 일부"}
    assert response.json()["version"] == 2


@pytest.mark.parametrize(
    "activities",
    [
        [{"id": "a9999999", "text": "이 경험에 없는 ID"}],
        [{"id": "PLACEHOLDER", "text": "a"}, {"id": "PLACEHOLDER", "text": "b"}],
    ],
    ids=["unknown-id", "duplicate-id"],
)
def test_patch_rejects_unknown_or_duplicate_activity_ids(client, activities):
    created = create(client)
    known = created["activities"][0]["id"]
    body = [{**a, "id": known if a["id"] == "PLACEHOLDER" else a["id"]} for a in activities]

    response = client.patch(
        f"{EXPERIENCES}/{created['id']}", json={"activities": body}, headers=HEADERS
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert client.get(f"{EXPERIENCES}/{created['id']}").json() == created


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"source_type": "resume_extract"},
        {"is_confirmed": False},
        {"version": 99},
        {"id": str(uuid.uuid4())},
        {"title": ""},
        {"activities": []},
    ],
    ids=["empty", "source_type", "is_confirmed", "version", "id", "blank-title", "no-activities"],
)
def test_patch_rejects_empty_immutable_or_invalid_bodies(client, body):
    created = create(client)

    response = client.patch(f"{EXPERIENCES}/{created['id']}", json=body, headers=HEADERS)

    assert response.status_code == 422
    assert client.get(f"{EXPERIENCES}/{created['id']}").json() == created


def test_patch_cannot_touch_other_users_experience(client, other_user):
    theirs = create(other_user, title="남의 것")

    response = client.patch(
        f"{EXPERIENCES}/{theirs['id']}", json={"title": "탈취"}, headers=HEADERS
    )

    assert response.status_code == 404
    assert other_user.get(f"{EXPERIENCES}/{theirs['id']}").json() == theirs


def test_responses_show_server_generated_values_even_if_session_never_expires(
    client, migrated_engine
):
    """운영의 세션은 commit 뒤에도 값을 만료시키지 않는다(expire_on_commit=False)."""
    with Session(migrated_engine, expire_on_commit=False) as session:
        client.app.dependency_overrides[get_db] = lambda: session
        created = create(client)
        response = client.patch(
            f"{EXPERIENCES}/{created['id']}", json={"title": "바뀐 제목"}, headers=HEADERS
        )

    body = response.json()
    assert created["created_at"] and created["updated_at"]  # 서버 기본값(now())을 읽어 왔다
    assert body["updated_at"] > created["updated_at"]  # 서버 onupdate 값이 반영됐다
    assert body["created_at"] == created["created_at"]


# ---- 삭제 --------------------------------------------------------------------


def test_delete_removes_only_that_experience(client):
    keep, remove = create(client, title="남길 것"), create(client, title="지울 것")

    response = client.delete(f"{EXPERIENCES}/{remove['id']}", headers=HEADERS)

    assert response.status_code == 204
    assert client.get(f"{EXPERIENCES}/{remove['id']}").status_code == 404
    assert [i["id"] for i in client.get(EXPERIENCES).json()["items"]] == [keep["id"]]
    assert client.delete(f"{EXPERIENCES}/{remove['id']}", headers=HEADERS).status_code == 404


def test_delete_cannot_remove_other_users_experience(client, other_user, db):
    theirs = create(other_user, title="남의 것")

    response = client.delete(f"{EXPERIENCES}/{theirs['id']}", headers=HEADERS)

    assert response.status_code == 404
    assert count(db) == 1


# ---- 인증·CSRF -----------------------------------------------------------------


def test_every_route_requires_a_session(auth_client):
    some_id = str(uuid.uuid4())
    calls = [
        ("GET", EXPERIENCES, None),
        ("POST", EXPERIENCES, card()),
        ("GET", f"{EXPERIENCES}/{some_id}", None),
        ("PATCH", f"{EXPERIENCES}/{some_id}", {"title": "x"}),
        ("DELETE", f"{EXPERIENCES}/{some_id}", None),
    ]

    for method, url, body in calls:
        response = auth_client.request(method, url, json=body, headers=HEADERS)
        assert response.status_code == 401, f"{method} {url}"


def test_changing_requests_need_a_matching_origin(client, db):
    created = create(client)
    url = f"{EXPERIENCES}/{created['id']}"

    for headers in ({}, {"Origin": "http://evil.example.com"}):
        assert client.post(EXPERIENCES, json=card(), headers=headers).status_code == 403
        assert client.patch(url, json={"title": "x"}, headers=headers).status_code == 403
        assert client.delete(url, headers=headers).status_code == 403

    assert count(db) == 1
    assert client.get(url).json() == created
