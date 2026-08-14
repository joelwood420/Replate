"""The API Gateway request/response adapter.

Thin by design, but worth testing directly: every handler funnels through it, and
a mistake here (a swallowed status code, a mis-parsed body) would show up as a
confusing failure in eight endpoints at once rather than one obvious one.
"""

import base64
import json

import pytest

from shared import http


# --- request parsing --------------------------------------------------------


def test_get_body_parses_json():
    event = {"body": json.dumps({"latitude": 1.0})}

    assert http.get_body(event) == {"latitude": 1.0}


def test_get_body_decodes_base64_payloads():
    """API Gateway base64-encodes bodies it considers binary."""
    raw = base64.b64encode(json.dumps({"saved": True}).encode()).decode()
    event = {"body": raw, "isBase64Encoded": True}

    assert http.get_body(event) == {"saved": True}


@pytest.mark.parametrize("body", [None, "", "not json", "[1, 2, 3]", '"a string"'])
def test_a_missing_or_unusable_body_reads_as_empty(body):
    """Matches the old behaviour: a malformed body must reach validation and
    produce a 400 with a useful message, not a 500."""
    assert http.get_body({"body": body}) == {}


def test_path_and_query_params():
    event = {"pathParameters": {"jobId": "job-1"}, "queryStringParameters": {"saved": "true"}}

    assert http.path_param(event, "jobId") == "job-1"
    assert http.query_param(event, "saved") == "true"


def test_absent_param_collections_do_not_raise():
    """API Gateway omits these keys entirely when there are none - it does not
    send empty objects."""
    assert http.path_param({}, "jobId") is None
    assert http.query_param({}, "limit", 20) == 20


def test_query_param_default_is_returned_when_missing():
    event = {"queryStringParameters": {"saved": "true"}}

    assert http.query_param(event, "limit", 20) == 20


@pytest.mark.parametrize("name", ["X-Debug-User-Oid", "x-debug-user-oid", "X-DEBUG-USER-OID"])
def test_header_lookup_is_case_insensitive(name):
    event = {"headers": {"x-debug-user-oid": "abc"}}

    assert http.get_header(event, name) == "abc"


def test_missing_header_returns_none():
    assert http.get_header({"headers": {}}, "Authorization") is None


# --- response building ------------------------------------------------------


def test_respond_serialises_the_body_and_sets_content_type():
    response = http.respond(200, {"ok": True})

    assert response["statusCode"] == 200
    assert response["headers"]["Content-Type"] == "application/json"
    assert json.loads(response["body"]) == {"ok": True}


def test_respond_merges_extra_headers():
    response = http.respond(429, {"error": "slow down"}, {"Retry-After": "60"})

    assert response["headers"]["Retry-After"] == "60"
    assert response["headers"]["Content-Type"] == "application/json"


def test_from_outcome_preserves_the_status_code():
    """Returning a bare dict from a Lambda behind an HTTP API auto-serialises it
    into a 200, silently losing every non-200 - hence the explicit shape."""
    outcome = {"status_code": 403, "body": {"error": "nope"}}

    response = http.from_outcome(outcome)

    assert response["statusCode"] == 403
    assert json.loads(response["body"]) == {"error": "nope"}


def test_from_outcome_carries_optional_headers():
    outcome = {
        "status_code": 429,
        "body": {"error": "quota spent", "retry_after_seconds": 60},
        "headers": {"Retry-After": "60"},
    }

    assert http.from_outcome(outcome)["headers"]["Retry-After"] == "60"


def test_from_outcome_tolerates_an_absent_headers_key():
    assert http.from_outcome({"status_code": 200, "body": {}})["statusCode"] == 200


def test_a_list_body_serialises(monkeypatch):
    """GET /api/jobs returns a bare array, not an object."""
    response = http.respond(200, [{"job_id": "a"}, {"job_id": "b"}])

    assert json.loads(response["body"]) == [{"job_id": "a"}, {"job_id": "b"}]
