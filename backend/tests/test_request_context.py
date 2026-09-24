import json
import logging
import re

import pytest

from app.logging_config import JsonFormatter
from tests.conftest import SENTINEL


def test_response_has_generated_request_id(client):
    response = client.get("/healthz")

    assert re.fullmatch(r"req_[0-9a-f]{32}", response.headers["X-Request-ID"])


def test_valid_incoming_request_id_is_kept(client):
    response = client.get("/healthz", headers={"X-Request-ID": "trace-abc_123.45"})

    assert response.headers["X-Request-ID"] == "trace-abc_123.45"


@pytest.mark.parametrize("bad_id", ["short", "has space 1234567", "bad!id-1234567", "a" * 65])
def test_invalid_incoming_request_id_is_replaced(client, bad_id):
    response = client.get("/healthz", headers={"X-Request-ID": bad_id})

    assert response.headers["X-Request-ID"] != bad_id
    assert re.fullmatch(r"req_[0-9a-f]{32}", response.headers["X-Request-ID"])


def test_unknown_route_uses_common_error_format(client):
    response = client.get("/nope")

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "not_found"
    assert error["details"] == []
    assert error["message"]
    assert error["request_id"] == response.headers["X-Request-ID"]


def test_too_long_text_is_reported_as_input_too_long_without_echoing_input(client):
    response = client.post("/_t/validate", json={"jd_text": SENTINEL * 3})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "input_too_long"
    assert error["details"] == [{"field": "jd_text", "issue": "string_too_long"}]
    assert SENTINEL not in response.text


def test_other_violations_are_validation_errors_even_with_a_too_long_field(client):
    missing = client.post("/_t/validate", json={})
    mixed = client.post("/_t/validate", json={"jd_text": SENTINEL * 3, "count": "abc"})

    for response in (missing, mixed):
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"
    issues = {detail["issue"] for detail in mixed.json()["error"]["details"]}
    assert issues == {"string_too_long", "int_parsing"}
    assert SENTINEL not in mixed.text


def test_app_error_carries_status_and_extra_fields(client):
    response = client.get("/_t/app-error")

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "duplicate_posting"
    assert error["existing_posting_id"] == "abc"
    assert error["request_id"] == response.headers["X-Request-ID"]


def test_unhandled_exception_returns_generic_500_with_request_id(client):
    response = client.get("/_t/boom")

    assert response.status_code == 500
    error = response.json()["error"]
    assert error["code"] == "internal_error"
    assert error["request_id"] == response.headers["X-Request-ID"]
    assert SENTINEL not in response.text


def test_access_log_has_method_path_status_and_duration_only(client, caplog):
    with caplog.at_level(logging.INFO, logger="jdive.access"):
        client.get("/healthz?code=SECRET-OAUTH-CODE&state=SECRET-STATE")

    records = [r for r in caplog.records if r.name == "jdive.access"]
    assert len(records) == 1
    line = json.loads(JsonFormatter().format(records[0]))
    assert line["method"] == "GET"
    assert line["path"] == "/healthz"
    assert line["status"] == 200
    assert line["duration_ms"] >= 0
    assert re.fullmatch(r"req_[0-9a-f]{32}", line["request_id"])
    assert "SECRET-OAUTH-CODE" not in json.dumps(line)
    assert "SECRET-STATE" not in json.dumps(line)


def test_json_formatter_emits_parseable_line_with_timestamp():
    record = logging.LogRecord(
        "jdive.app", logging.WARNING, __file__, 1, "안녕 %s", ("세계",), None
    )

    line = json.loads(JsonFormatter().format(record))

    assert line["level"] == "WARNING"
    assert line["logger"] == "jdive.app"
    assert line["message"] == "안녕 세계"
    assert line["ts"].endswith("+00:00")
