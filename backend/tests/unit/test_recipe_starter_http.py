import asyncio
import json
from unittest.mock import MagicMock

from shared.models import JobStatus, MatchMethod
from triggers import recipe_starter_http as starter

_OWNER = "11111111-1111-1111-1111-111111111111"
_VISION_GUESS = {"dish_name_guess": "Pad Thai", "cuisine_guess": "Thai", "elements": []}


class _ConnectionCtx:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, *exc_info):
        return False


def _row(status=JobStatus.IDENTIFIED, owner=_OWNER, vision_guess=_VISION_GUESS):
    return MagicMock(
        UserId=owner,
        Status=status,
        DishName="Pad Thai Goong",
        Cuisine="Thai",
        Confidence=0.8,
        MatchedRestaurantId="place-1",
        MatchedMenuItemId=None,
        MatchConfidence=0.91,
        MatchMethod=MatchMethod.MENU_MATCHED,
        VisionGuessJson=json.dumps(vision_guess) if vision_guess is not None else None,
    )


def _patch_conn(monkeypatch, row):
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = row
    monkeypatch.setattr(starter.db, "get_connection", lambda: _ConnectionCtx(conn))
    return conn


def test_returns_404_for_unknown_job(monkeypatch):
    _patch_conn(monkeypatch, None)

    outcome = starter.build_recipe_input("job-1", _OWNER)

    assert outcome == {"status_code": 404, "body": {"error": "Job not found"}}


def test_returns_403_when_caller_does_not_own_the_job(monkeypatch):
    _patch_conn(monkeypatch, _row(owner="22222222-2222-2222-2222-222222222222"))

    outcome = starter.build_recipe_input("job-1", _OWNER)

    assert outcome["status_code"] == 403


def test_returns_409_when_recipe_already_generated(monkeypatch):
    conn = _patch_conn(monkeypatch, _row(status=JobStatus.COMPLETED))

    outcome = starter.build_recipe_input("job-1", _OWNER)

    assert outcome["status_code"] == 409
    # Must not flip an already-Completed job back to Generating.
    assert not [c for c in conn.cursor().execute.call_args_list if "UPDATE Jobs" in c.args[0]]


def test_returns_409_when_generation_already_in_flight(monkeypatch):
    _patch_conn(monkeypatch, _row(status=JobStatus.GENERATING))

    assert starter.build_recipe_input("job-1", _OWNER)["status_code"] == 409


def test_returns_409_when_stage_one_has_not_finished(monkeypatch):
    _patch_conn(monkeypatch, _row(status=JobStatus.PROCESSING))

    assert starter.build_recipe_input("job-1", _OWNER)["status_code"] == 409


def test_returns_409_when_vision_guess_was_never_persisted(monkeypatch):
    """Only reachable for rows written before the VisionGuessJson column existed."""
    _patch_conn(monkeypatch, _row(vision_guess=None))

    outcome = starter.build_recipe_input("job-1", _OWNER)

    assert outcome["status_code"] == 409
    assert "vision analysis" in outcome["body"]["error"]


def test_marks_generating_and_builds_orchestration_input(monkeypatch):
    conn = _patch_conn(monkeypatch, _row())

    outcome = starter.build_recipe_input("job-1", _OWNER)

    updates = [c for c in conn.cursor().execute.call_args_list if "UPDATE Jobs" in c.args[0]]
    assert len(updates) == 1
    assert updates[0].args[1] == JobStatus.GENERATING

    assert outcome["orchestration_input"]["job_id"] == "job-1"
    assert outcome["orchestration_input"]["vision_guess"] == _VISION_GUESS
    assert outcome["orchestration_input"]["match_result"] == {
        "dish_name": "Pad Thai Goong",
        "cuisine": "Thai",
        "vision_confidence": 0.8,
        "matched_restaurant_id": "place-1",
        "matched_menu_item_id": None,
        "match_confidence": 0.91,
        "match_method": MatchMethod.MENU_MATCHED,
    }


def test_handle_request_starts_orchestration_on_a_distinct_instance_id(monkeypatch):
    monkeypatch.setattr(
        starter,
        "build_recipe_input",
        lambda job_id, user_oid: {"orchestration_input": {"job_id": job_id}},
    )
    started = {}

    async def fake_start_new(name, instance_id=None, client_input=None):
        started.update(name=name, instance_id=instance_id, client_input=client_input)
        return instance_id

    client = MagicMock(start_new=fake_start_new)

    outcome = asyncio.run(starter.handle_request("job-1", _OWNER, client))

    assert started["name"] == "recipe_orchestrator_trigger"
    # Stage 1 already used the bare job id, so reusing it would collide.
    assert started["instance_id"] == "job-1:recipe"
    assert outcome == {"status_code": 202, "body": {"job_id": "job-1", "status": JobStatus.GENERATING}}


def test_handle_request_does_not_start_orchestration_when_validation_fails(monkeypatch):
    monkeypatch.setattr(
        starter,
        "build_recipe_input",
        lambda job_id, user_oid: {"status_code": 409, "body": {"error": "nope"}},
    )
    client = MagicMock()

    outcome = asyncio.run(starter.handle_request("job-1", _OWNER, client))

    assert outcome == {"status_code": 409, "body": {"error": "nope"}}
    client.start_new.assert_not_called()
