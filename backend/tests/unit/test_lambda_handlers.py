"""End-to-end checks on the Lambda entry points themselves.

The per-endpoint tests exercise `run()`; these exercise `handler()` - the adapter
that pulls path params, query strings, body and auth out of an API Gateway event
and turns the outcome back into a gateway response. That seam is where a port
like this breaks quietly, so it gets its own coverage.

Activity handlers are here too, because two of them (the restaurant-lookup pair
and the embeddings query) reshape their input or output for the state machine
rather than passing it straight through.
"""

import json

import pytest

from activities import (
    geocode_restaurant_candidates,
    persist_job_result,
    query_culinary_embeddings,
    select_restaurant_candidate,
)
from shared import models, repository
from shared.models import JobStatus
from triggers import job_result_http, job_save_http, jobs_list_http, upload_http

_OWNER = "user-oid-1"


def _event(**parts):
    base = {"headers": {"X-Debug-User-Oid": _OWNER}}
    base.update(parts)
    return base


@pytest.fixture(autouse=True)
def stub_storage(monkeypatch):
    monkeypatch.setattr(
        upload_http.storage,
        "generate_upload_url",
        lambda: {"key": "uploads/photo.jpg", "upload_url": "https://s3/put", "expiry": "z"},
    )
    for module in (job_result_http, jobs_list_http):
        monkeypatch.setattr(module.storage, "generate_read_url", lambda key: f"{key}?sig=abc")


# --- HTTP handlers ----------------------------------------------------------


def test_upload_handler_reads_the_body_and_returns_201(ddb_table):
    event = _event(body=json.dumps({"latitude": 40.7, "longitude": -74.0}))

    response = upload_http.handler(event)

    assert response["statusCode"] == 201
    body = json.loads(response["body"])
    assert body["image_key"] == "uploads/photo.jpg"
    assert repository.get_job(body["job_id"])["user_id"] == _OWNER


def test_upload_handler_returns_400_for_a_malformed_body(ddb_table):
    response = upload_http.handler(_event(body="{not json"))

    assert response["statusCode"] == 400


def test_job_result_handler_reads_the_path_parameter(ddb_table):
    repository.create_job(
        job_id="job-1", user_oid=_OWNER, status=JobStatus.QUEUED, image_key="uploads/p.jpg"
    )

    response = job_result_http.handler(_event(pathParameters={"jobId": "job-1"}))

    assert response["statusCode"] == 200
    assert json.loads(response["body"])["job_id"] == "job-1"


def test_job_result_handler_returns_403_not_200_for_another_users_job(ddb_table):
    """The status code has to survive the adapter - a bare dict return would have
    made this a 200."""
    repository.create_job(
        job_id="job-1", user_oid="someone-else", status=JobStatus.QUEUED, image_key="uploads/p.jpg"
    )

    response = job_result_http.handler(_event(pathParameters={"jobId": "job-1"}))

    assert response["statusCode"] == 403


def test_jobs_list_handler_parses_query_parameters(ddb_table):
    for index in range(3):
        repository.create_job(
            job_id=f"job-{index}", user_oid=_OWNER, status=JobStatus.QUEUED, image_key="p.jpg"
        )
    repository.update_job("job-0", is_saved=True)

    response = jobs_list_http.handler(_event(queryStringParameters={"saved": "true", "limit": "5"}))

    assert [job["job_id"] for job in json.loads(response["body"])] == ["job-0"]


def test_jobs_list_handler_falls_back_on_a_junk_limit(ddb_table):
    repository.create_job(
        job_id="job-1", user_oid=_OWNER, status=JobStatus.QUEUED, image_key="p.jpg"
    )

    response = jobs_list_http.handler(_event(queryStringParameters={"limit": "banana"}))

    assert response["statusCode"] == 200
    assert len(json.loads(response["body"])) == 1


def test_job_save_handler_defaults_saved_to_true(ddb_table):
    repository.create_job(
        job_id="job-1", user_oid=_OWNER, status=JobStatus.IDENTIFIED, image_key="p.jpg"
    )

    response = job_save_http.handler(_event(pathParameters={"jobId": "job-1"}, body="{}"))

    assert json.loads(response["body"])["is_saved"] is True


def test_a_throttled_upload_carries_the_retry_after_header(ddb_table, monkeypatch):
    monkeypatch.setattr(
        upload_http.rate_limit,
        "check_and_consume",
        lambda oid, action: {"allowed": False, "error": "no", "retry_after_seconds": 42},
    )

    response = upload_http.handler(_event(body=json.dumps({"latitude": 1.0, "longitude": 2.0})))

    assert response["statusCode"] == 429
    assert response["headers"]["Retry-After"] == "42"


# --- activity handlers ------------------------------------------------------


def test_geocode_handler_wraps_candidates_in_the_state_machine_envelope(ddb_table):
    result = geocode_restaurant_candidates.handler(
        {"job_id": "job-1", "latitude": 40.7128, "longitude": -74.0060}
    )

    assert result["candidate_found"] is True
    assert result["top_candidate"] == result["candidates"][0]
    assert result["restaurant_id"] == result["candidates"][0]["restaurant_id"]


def test_geocode_handler_reports_no_candidate_without_failing(ddb_table):
    """No restaurant near those coordinates is a valid outcome - the Choice state
    reads candidate_found, so it must be present and false rather than absent."""
    result = geocode_restaurant_candidates.handler(
        {"job_id": "job-1", "latitude": 0.0, "longitude": 0.0}
    )

    assert result["candidate_found"] is False
    assert result["top_candidate"] is None
    assert result["restaurant_id"] is None


def test_select_handler_emits_the_same_envelope_shape(ddb_table):
    """Both branches feed one Choice state, so their outputs must agree."""
    repository.upsert_restaurant("place-1", "Luigi's", "123 Main St", 40.7, -74.0, None)

    selected = select_restaurant_candidate.handler({"job_id": "job-1", "restaurant_id": "place-1"})
    geocoded = geocode_restaurant_candidates.handler(
        {"job_id": "job-2", "latitude": 40.7128, "longitude": -74.0060}
    )

    assert set(selected) == set(geocoded) == set(models.candidate_envelope([]))


def test_embeddings_handler_prefers_the_matched_dish_name(ddb_table):
    query = query_culinary_embeddings.build_query_text(
        {"dish_name": "Pad Thai Goong"}, {"dish_name_guess": "Noodles"}
    )

    assert query == "Pad Thai Goong"


def test_embeddings_handler_falls_back_to_the_vision_guess(ddb_table):
    """A vision-only outcome has no matched dish name at all."""
    query = query_culinary_embeddings.build_query_text(
        {"dish_name": None}, {"dish_name_guess": "Noodles"}
    )

    assert query == "Noodles"


@pytest.mark.parametrize(
    "match_result,vision_guess", [(None, None), ({}, {}), ({"dish_name": None}, {})]
)
def test_embeddings_query_text_never_raises_on_missing_input(match_result, vision_guess):
    assert query_culinary_embeddings.build_query_text(match_result, vision_guess) == ""


def test_persist_handlers_return_the_new_status(ddb_table):
    """The state machine does not read these, but a Lambda returning None makes an
    execution history far harder to read."""
    repository.create_job(
        job_id="job-1", user_oid=_OWNER, status=JobStatus.PROCESSING, image_key="p.jpg"
    )

    result = persist_job_result.mark_job_failed_handler({"job_id": "job-1", "error_message": "x"})

    assert result == {"job_id": "job-1", "status": JobStatus.FAILED}
