"""공고 저장·중복 감지·조회(1단계). 소유권, 검증, jd_hash 정규화, 원문 비노출."""

import hashlib
import logging
import unicodedata
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import JobPosting, User
from tests.conftest import SENTINEL
from tests.fake_google import ORIGIN, sign_in

POSTINGS = "/api/v1/job-postings"
HEADERS = {"Origin": ORIGIN}
JD_LINES = [f"요구사항 {i}: 가상의 조건을 설명하는 한 줄입니다." for i in range(10)]
JD_TEXT = "\n".join(JD_LINES)


def posting(**overrides) -> dict:
    body = {
        "job_title": "AI Engineer",
        "company_name": "예시 기업",
        "source_url": "https://example.com/jobs/1",
        "jd_text": JD_TEXT,
    }
    return {**body, **overrides}


@pytest.fixture
def client(auth_client, fake_google):
    sign_in(auth_client, fake_google)
    return auth_client


@pytest.fixture
def other_user(make_auth_client, fake_google, client):
    fake_google.sub, fake_google.email = "google-sub-2", "other@example.com"
    other = make_auth_client()
    sign_in(other, fake_google)
    return other


def save(client, **overrides):
    return client.post(POSTINGS, json=posting(**overrides), headers=HEADERS)


def saved(client, **overrides) -> dict:
    response = save(client, **overrides)
    assert response.status_code == 201, response.text
    return response.json()


def count(db) -> int:
    return db.scalar(select(func.count()).select_from(JobPosting))


def expected_hash(text: str) -> str:
    return hashlib.sha256(" ".join(unicodedata.normalize("NFC", text).split()).encode()).hexdigest()


# ---- 저장 --------------------------------------------------------------------


def test_create_returns_the_saved_posting_and_stores_the_hash(client, db):
    response = save(client)

    assert response.status_code == 201
    body = response.json()
    assert body["job_title"] == "AI Engineer"
    assert body["company_name"] == "예시 기업"
    assert body["source_url"] == "https://example.com/jobs/1"
    assert body["jd_text"] == JD_TEXT
    assert body["id"] and body["created_at"]
    assert "user_id" not in body and "jd_hash" not in body

    row = db.scalar(select(JobPosting))
    assert str(row.id) == body["id"]
    assert row.user_id == db.scalar(select(User.id))
    assert row.jd_hash == expected_hash(JD_TEXT)


@pytest.mark.parametrize("url", [None, "", "   "], ids=["null", "empty", "blank"])
def test_source_url_is_optional(client, url):
    assert saved(client, source_url=url)["source_url"] is None


def test_source_url_can_be_left_out(client):
    body = {k: v for k, v in posting().items() if k != "source_url"}

    response = client.post(POSTINGS, json=body, headers=HEADERS)

    assert response.status_code == 201
    assert response.json()["source_url"] is None


def test_create_trims_surrounding_whitespace(client):
    body = saved(
        client, job_title="  AI Engineer ", company_name=" 예시 ", jd_text=f"\n\n{JD_TEXT}\n "
    )

    assert (body["job_title"], body["company_name"]) == ("AI Engineer", "예시")
    assert body["jd_text"] == JD_TEXT


@pytest.mark.parametrize(
    "url",
    ["http://example.com/a", "https://example.com/a?x=1&y=2#top", "HTTPS://Example.com/Jobs"],
)
def test_source_url_accepts_http_and_https(client, url):
    assert saved(client, source_url=url)["source_url"] == url


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "ftp://example.com/a",
        "//example.com/a",
        "example.com/jobs",
        "https://",
        "https://exa mple.com/a",
    ],
    ids=["javascript", "data", "ftp", "no-scheme-slashes", "no-scheme", "no-host", "space"],
)
def test_source_url_rejects_anything_but_web_addresses(client, db, url):
    response = save(client, source_url=url)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert "source_url" in [d["field"] for d in response.json()["error"]["details"]]
    assert count(db) == 0


# (요청 덮어쓰기, 오류가 나는 필드, 오류 코드) — 글자 수 초과만 input_too_long 이다(§1.1)
INVALID_POSTINGS = [
    pytest.param({"job_title": None}, "job_title", "validation_error", id="no-title"),
    pytest.param({"job_title": "  "}, "job_title", "validation_error", id="blank-title"),
    pytest.param({"job_title": "가" * 151}, "job_title", "input_too_long", id="title-long"),
    pytest.param({"company_name": None}, "company_name", "validation_error", id="no-company"),
    pytest.param({"company_name": "가" * 101}, "company_name", "input_too_long", id="company"),
    pytest.param({"jd_text": None}, "jd_text", "validation_error", id="no-jd"),
    pytest.param({"jd_text": "가" * 199}, "jd_text", "validation_error", id="jd-199"),
    pytest.param({"jd_text": "x" * 150 + " " * 100}, "jd_text", "validation_error", id="jd-pad"),
    pytest.param({"jd_text": "가" * 15001}, "jd_text", "input_too_long", id="jd-15001"),
    pytest.param(
        {"source_url": "https://example.com/" + "a" * 2000},
        "source_url",
        "input_too_long",
        id="url-long",
    ),
    pytest.param({"jd_hash": "abc"}, "jd_hash", "validation_error", id="client-hash"),
    pytest.param({"user_id": str(uuid.uuid4())}, "user_id", "validation_error", id="user-id"),
]


@pytest.mark.parametrize(("overrides", "field", "code"), INVALID_POSTINGS)
def test_create_rejects_invalid_input(client, db, overrides, field, code):
    body = {k: v for k, v in posting(**overrides).items() if v is not None}

    response = client.post(POSTINGS, json=body, headers=HEADERS)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == code
    assert field in [detail["field"] for detail in error["details"]]
    assert count(db) == 0


@pytest.mark.parametrize("length", [200, 15000])
def test_jd_text_length_limits_are_inclusive(client, length):
    assert save(client, jd_text="가" * length).status_code == 201


def test_jd_text_never_appears_in_responses_or_logs(client, caplog):
    caplog.set_level(logging.DEBUG)
    jd = (SENTINEL + " ") * 12
    too_long = (SENTINEL + " ") * 1000

    first = save(client, jd_text=jd)
    duplicate = save(client, jd_text=jd)
    rejected = save(client, jd_text=too_long)

    assert (first.status_code, duplicate.status_code, rejected.status_code) == (201, 409, 422)
    for response in (duplicate, rejected):
        assert SENTINEL not in response.text
    assert SENTINEL not in caplog.text + "".join(str(vars(r)) for r in caplog.records)


# ---- 중복 감지 ---------------------------------------------------------------


def test_saving_the_same_jd_again_returns_409_with_the_existing_id(client, db):
    first = saved(client)

    response = save(client)

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "duplicate_posting"
    assert error["existing_posting_id"] == first["id"]
    assert error["message"] and error["request_id"]
    assert count(db) == 1


def test_a_duplicate_is_a_duplicate_whatever_the_title_or_company(client):
    first = saved(client)

    response = save(client, job_title="다른 공고명", company_name="다른 회사", source_url=None)

    assert response.status_code == 409
    assert response.json()["error"]["existing_posting_id"] == first["id"]


VARIANTS = {
    "crlf": JD_TEXT.replace("\n", "\r\n"),
    "blank-lines": "\n\n".join(JD_LINES),
    "padding": f"  {JD_TEXT}  \n",
    "tabs-and-spaces": JD_TEXT.replace(" ", "\t  "),
    "decomposed-hangul": unicodedata.normalize("NFD", JD_TEXT),
}


@pytest.mark.parametrize("variant", VARIANTS.values(), ids=VARIANTS.keys())
def test_whitespace_and_unicode_form_do_not_make_a_new_jd(client, db, variant):
    first = saved(client)

    response = save(client, jd_text=variant)

    assert response.status_code == 409
    assert response.json()["error"]["existing_posting_id"] == first["id"]
    assert count(db) == 1


def test_a_changed_word_is_a_different_jd(client, db):
    saved(client)

    response = save(client, jd_text=JD_TEXT.replace("조건", "요건", 1))

    assert response.status_code == 201
    assert count(db) == 2


def test_other_users_can_save_the_same_jd_and_never_see_each_others_ids(client, other_user, db):
    mine = saved(client)

    theirs = save(other_user)
    assert theirs.status_code == 201
    assert theirs.json()["id"] != mine["id"]

    again = save(other_user)
    assert again.status_code == 409
    assert again.json()["error"]["existing_posting_id"] == theirs.json()["id"]
    assert count(db) == 2


def test_a_duplicate_does_not_break_the_next_request(client):
    saved(client)
    assert save(client).status_code == 409

    assert save(client, jd_text=JD_TEXT + " 추가 문장").status_code == 201


# ---- 조회 --------------------------------------------------------------------


def test_list_is_empty_at_first(client):
    response = client.get(POSTINGS)

    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_list_shows_own_postings_newest_first_without_the_jd_text(client, other_user):
    older = saved(client, job_title="먼저 저장", jd_text=JD_TEXT + " 1")
    newer = saved(client, job_title="나중에 저장", jd_text=JD_TEXT + " 2")
    save(other_user, job_title="남의 공고")

    items = client.get(POSTINGS).json()["items"]

    assert [item["id"] for item in items] == [newer["id"], older["id"]]
    assert set(items[0]) == {"id", "job_title", "company_name", "source_url", "created_at"}
    assert [i["job_title"] for i in other_user.get(POSTINGS).json()["items"]] == ["남의 공고"]


def test_get_returns_the_posting_with_its_jd_text(client):
    created = saved(client)

    response = client.get(f"{POSTINGS}/{created['id']}")

    assert response.status_code == 200
    assert response.json() == created


def test_postings_are_still_there_after_signing_in_again(client, make_auth_client, fake_google):
    created = saved(client)
    fake_google.sub, fake_google.email = "google-sub-1", "user@example.com"

    returning = make_auth_client()
    sign_in(returning, fake_google)

    assert [i["id"] for i in returning.get(POSTINGS).json()["items"]] == [created["id"]]


def test_get_returns_404_for_missing_and_for_other_users(client, other_user):
    theirs = saved(other_user)

    for posting_id in (theirs["id"], str(uuid.uuid4())):
        response = client.get(f"{POSTINGS}/{posting_id}")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"


def test_get_rejects_a_malformed_id(client):
    assert client.get(f"{POSTINGS}/not-a-uuid").status_code == 422


def test_server_generated_created_at_is_returned_even_if_session_never_expires(
    client, migrated_engine
):
    """운영의 세션은 commit 뒤에도 값을 만료시키지 않는다(expire_on_commit=False)."""
    with Session(migrated_engine, expire_on_commit=False) as session:
        client.app.dependency_overrides[get_db] = lambda: session
        response = save(client)

    assert response.status_code == 201
    assert response.json()["created_at"]


# ---- 인증·CSRF -----------------------------------------------------------------


def test_every_route_requires_a_session(auth_client):
    calls = [
        ("GET", POSTINGS, None),
        ("POST", POSTINGS, posting()),
        ("GET", f"{POSTINGS}/{uuid.uuid4()}", None),
    ]

    for method, url, body in calls:
        response = auth_client.request(method, url, json=body, headers=HEADERS)
        assert response.status_code == 401, f"{method} {url}"


def test_saving_needs_a_matching_origin(client, db):
    for headers in ({}, {"Origin": "http://evil.example.com"}):
        response = client.post(POSTINGS, json=posting(), headers=headers)
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "csrf_origin_mismatch"

    assert count(db) == 0
