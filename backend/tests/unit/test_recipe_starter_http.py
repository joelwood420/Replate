import datetime

from shared import ddb, repository
from shared.models import JobStatus, MatchMethod
from triggers import recipe_starter_http as starter

_OWNER = "11111111-1111-1111-1111-111111111111"
_VISION_GUESS = {"dish_name_guess": "Pad Thai", "cuisine_guess": "Thai", "elements": []}
_MATCH_RESULT = {
    "dish_name": "Pad Thai Goong",
    "dish_description": "prawns, tamarind, peanuts",
    "cuisine": "Thai",
    "vision_confidence": 0.8,
    "matched_restaurant_id": "place-1",
    "matched_menu_item_id": None,
    "match_confidence": 0.91,
    "match_method": MatchMethod.MENU_MATCHED,
}


def _job(status=JobStatus.IDENTIFIED, owner=_OWNER, vision_guess=_VISION_GUESS):
    repository.create_job(
        job_id="job-1", user_oid=owner, status=status, image_key="uploads/p.jpg"
    )
    repository.put_job_result("job-1", _MATCH_RESULT, vision_guess)


def _spend_recipe_quota(call_count):
    bucket = datetime.datetime.now(datetime.timezone.utc).replace(minute=0, second=0, microsecond=0)
    ddb.put(
        {
            "PK": ddb.rate_pk(_OWNER),
            "SK": ddb.rate_sk("recipe", bucket.strftime("%Y-%m-%dT%H")),
            "call_count": call_count,
            "expires_at": int((bucket + datetime.timedelta(hours=26)).timestamp()),
        }
    )


def test_returns_404_for_unknown_job(ddb_table):
    outcome = starter.build_recipe_input("job-1", _OWNER)

    assert outcome == {"status_code": 404, "body": {"error": "Job not found"}}


def test_returns_403_when_caller_does_not_own_the_job(ddb_table):
    _job(owner="22222222-2222-2222-2222-222222222222")

    assert starter.build_recipe_input("job-1", _OWNER)["status_code"] == 403


def test_returns_409_when_recipe_already_generated(ddb_table):
    _job(status=JobStatus.COMPLETED)

    outcome = starter.build_recipe_input("job-1", _OWNER)

    assert outcome["status_code"] == 409
    # Must not flip an already-Completed job back to Generating.
    assert repository.get_job("job-1")["status"] == JobStatus.COMPLETED


def test_returns_409_when_generation_already_in_flight(ddb_table):
    _job(status=JobStatus.GENERATING)

    assert starter.build_recipe_input("job-1", _OWNER)["status_code"] == 409


def test_returns_409_when_stage_one_has_not_finished(ddb_table):
    _job(status=JobStatus.PROCESSING)

    assert starter.build_recipe_input("job-1", _OWNER)["status_code"] == 409


def test_returns_409_when_vision_guess_was_never_persisted(ddb_table):
    """Only reachable for jobs written before the vision guess was persisted."""
    _job(vision_guess=None)

    outcome = starter.build_recipe_input("job-1", _OWNER)

    assert outcome["status_code"] == 409
    assert "vision analysis" in outcome["body"]["error"]


def test_marks_generating_and_builds_orchestration_input(ddb_table):
    _job()

    outcome = starter.build_recipe_input("job-1", _OWNER)

    assert repository.get_job("job-1")["status"] == JobStatus.GENERATING
    assert outcome["orchestration_input"]["job_id"] == "job-1"
    assert outcome["orchestration_input"]["vision_guess"] == _VISION_GUESS
    assert outcome["orchestration_input"]["match_result"] == _MATCH_RESULT


def test_starting_generation_clears_a_previous_error(ddb_table):
    """A retry after a failed generation should not keep showing the old error."""
    _job()
    repository.update_job("job-1", error_message="generator exploded")

    starter.build_recipe_input("job-1", _OWNER)

    assert repository.get_job("job-1")["error_message"] is None


def test_handle_request_starts_the_recipe_machine_on_the_built_name(monkeypatch):
    # build_recipe_input owns the execution name (derived from the job's Identified
    # updated_at so retries get a fresh, non-colliding name); handle_request just
    # uses it.
    monkeypatch.setattr(
        starter,
        "build_recipe_input",
        lambda job_id, user_oid: {
            "orchestration_input": {"job_id": job_id},
            "execution_name": f"{job_id}-recipe-2026-08-18T00-00-00-000000-00-00",
        },
    )
    monkeypatch.setenv("RECIPE_STATE_MACHINE_ARN", "arn:aws:states:::stateMachine:recipe")
    started = {}

    def fake_start(arn, name, payload):
        started.update(arn=arn, name=name, payload=payload)
        return True

    monkeypatch.setattr(starter.sfn, "start_execution", fake_start)

    outcome = starter.handle_request("job-1", _OWNER)

    assert started["arn"] == "arn:aws:states:::stateMachine:recipe"
    assert started["name"] == "job-1-recipe-2026-08-18T00-00-00-000000-00-00"
    assert outcome == {"status_code": 202, "body": {"job_id": "job-1", "status": JobStatus.GENERATING}}


def test_execution_name_is_distinct_across_retries(ddb_table):
    """A fresh Identified state (new updated_at) yields a new execution name, so a
    retried generation is not blocked by Step Functions' 90-day name reuse rule."""
    _job()
    first = starter.build_recipe_input("job-1", _OWNER)["execution_name"]

    # Revert to Identified with a new updated_at, as MarkRecipeFailed would.
    repository.update_job("job-1", status=JobStatus.IDENTIFIED)
    second = starter.build_recipe_input("job-1", _OWNER)["execution_name"]

    assert first != second
    assert first.startswith("job-1-recipe-")


def test_a_double_tap_is_still_accepted(monkeypatch):
    """An already-existing execution means the work is in flight, not an error."""
    monkeypatch.setattr(
        starter,
        "build_recipe_input",
        lambda job_id, user_oid: {
            "orchestration_input": {"job_id": job_id},
            "execution_name": f"{job_id}-recipe-x",
        },
    )
    monkeypatch.setattr(starter.sfn, "start_execution", lambda *a, **k: False)

    outcome = starter.handle_request("job-1", _OWNER)

    assert outcome["status_code"] == 202


def test_a_rejected_request_starts_nothing(monkeypatch):
    monkeypatch.setattr(
        starter,
        "build_recipe_input",
        lambda job_id, user_oid: {"status_code": 404, "body": {"error": "Job not found"}},
    )

    def explode(*args, **kwargs):
        raise AssertionError("must not start an execution for a rejected request")

    monkeypatch.setattr(starter.sfn, "start_execution", explode)

    assert starter.handle_request("job-1", _OWNER)["status_code"] == 404


def test_returns_429_when_the_generation_quota_is_spent(ddb_table, monkeypatch):
    monkeypatch.setenv("RECIPE_RATE_LIMIT_PER_HOUR", "2")
    _job()
    _spend_recipe_quota(2)

    outcome = starter.build_recipe_input("job-1", _OWNER)

    assert outcome["status_code"] == 429
    assert "2 recipe generations" in outcome["body"]["error"]
    assert outcome["headers"]["Retry-After"] == str(outcome["body"]["retry_after_seconds"])
    # The job must stay Identified so the user can retry once the window reopens.
    assert repository.get_job("job-1")["status"] == JobStatus.IDENTIFIED


def test_a_rejected_request_does_not_spend_the_quota(ddb_table, monkeypatch):
    """404/403/409 all come before the quota check - being told 'no' should not
    cost the user one of their generations."""
    monkeypatch.setenv("RECIPE_RATE_LIMIT_PER_HOUR", "2")
    _job(status=JobStatus.COMPLETED)

    starter.build_recipe_input("job-1", _OWNER)

    assert ddb.query_prefix(ddb.rate_pk(_OWNER), "recipe#") == []


def test_a_successful_start_consumes_one_generation(ddb_table):
    _job()

    starter.build_recipe_input("job-1", _OWNER)

    rows = ddb.query_prefix(ddb.rate_pk(_OWNER), "recipe#")
    assert sum(row["call_count"] for row in rows) == 1


def test_scan_quota_is_untouched_by_generation(ddb_table):
    """Separate quotas per pipeline stage - see shared/rate_limit.py."""
    _job()

    starter.build_recipe_input("job-1", _OWNER)

    assert ddb.query_prefix(ddb.rate_pk(_OWNER), "scan#") == []
