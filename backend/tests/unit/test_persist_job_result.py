from unittest.mock import MagicMock

from activities import persist_job_result
from shared.models import JobStatus, MatchMethod


def test_writes_job_results_and_dish_element_rows():
    conn = MagicMock()
    activity_input = {
        "job_id": "job-123",
        "match_result": {
            "dish_name": "Margherita Pizza",
            "cuisine": "Italian",
            "vision_confidence": 0.8,
            "matched_restaurant_id": "stub-1",
            "matched_menu_item_id": "item-1",
            "match_confidence": 0.9,
            "match_method": MatchMethod.MENU_MATCHED,
        },
        "recreation": {
            "elements": [
                {
                    "name": "Crust",
                    "description": "desc",
                    "sort_order": 1,
                    "ingredients": [{"ingredient_name": "Flour", "amount": "2", "unit": "cup", "sort_order": 1}],
                    "steps": [{"step_number": 1, "instruction": "Mix and knead."}],
                }
            ]
        },
    }

    persist_job_result._execute(activity_input, conn)

    executed_sql = [c.args[0] for c in conn.cursor().execute.call_args_list]
    assert any("INSERT INTO JobResults" in s for s in executed_sql)
    assert any("INSERT INTO DishElements" in s for s in executed_sql)
    assert any("INSERT INTO ElementIngredients" in s for s in executed_sql)
    assert any("INSERT INTO ElementSteps" in s for s in executed_sql)


def test_updates_job_status_to_completed():
    conn = MagicMock()
    activity_input = {
        "job_id": "job-123",
        "match_result": {
            "dish_name": "X",
            "cuisine": "Y",
            "vision_confidence": 0.5,
            "matched_restaurant_id": None,
            "matched_menu_item_id": None,
            "match_confidence": 0.0,
            "match_method": MatchMethod.VISION_ONLY_LOW,
        },
        "recreation": {"elements": []},
    }

    persist_job_result._execute(activity_input, conn)

    update_call = [c for c in conn.cursor().execute.call_args_list if "UPDATE Jobs" in c.args[0]]
    assert len(update_call) == 1
    assert update_call[0].args[1] == JobStatus.COMPLETED
    assert update_call[0].args[2] == "job-123"


def test_mark_job_failed_sets_status_and_error_message():
    conn = MagicMock()

    persist_job_result._execute_mark_failed({"job_id": "job-123", "error_message": "boom"}, conn)

    call = conn.cursor().execute.call_args
    assert "UPDATE Jobs" in call.args[0]
    assert call.args[1] == JobStatus.FAILED
    assert call.args[2] == "boom"
    assert call.args[3] == "job-123"
