"""Structural tests over the Step Functions definitions.

These replace tests/unit/test_orchestrator.py, which drove the Durable generator
directly and asserted on the order of `call_activity` calls. The state machines
are now data, so the equivalent assertions are about the shape of that data - and
they catch a class of bug the old tests could not: a `Next` pointing at a state
name that does not exist is a deploy-time failure in ASL, but a silent typo in a
JSON file until something validates it.

What these do NOT cover is actually executing a definition. That needs Step
Functions Local or a real deployment, and belongs in the integration suite.
"""

import json
import pathlib

import pytest

STATEMACHINE_DIR = pathlib.Path(__file__).resolve().parents[2] / "statemachines"

IDENTIFY = json.loads((STATEMACHINE_DIR / "dish-identify.asl.json").read_text(encoding="utf-8"))
RECIPE = json.loads((STATEMACHINE_DIR / "dish-recipe.asl.json").read_text(encoding="utf-8"))


def _walk(states: dict, prefix: str = ""):
    """Yield (qualified_name, state) for every state, descending into Parallel branches."""
    for name, state in states.items():
        yield f"{prefix}{name}", state
        for branch in state.get("Branches", []):
            yield from _walk(branch["States"], prefix=f"{prefix}{name}/")


def _transitions(state: dict) -> list[str]:
    targets = []
    if "Next" in state:
        targets.append(state["Next"])
    if "Default" in state:
        targets.append(state["Default"])
    for choice in state.get("Choices", []):
        if "Next" in choice:
            targets.append(choice["Next"])
    for catcher in state.get("Catch", []):
        targets.append(catcher["Next"])
    return targets


def _scopes(definition: dict):
    """Every independent state-name scope: the top level, plus each Parallel branch."""
    yield definition["StartAt"], definition["States"]
    for _, state in _walk(definition["States"]):
        for branch in state.get("Branches", []):
            yield branch["StartAt"], branch["States"]


def _resources(definition: dict) -> set[str]:
    return {
        state["Resource"]
        for _, state in _walk(definition["States"])
        if state.get("Type") == "Task"
    }


# --- graph consistency, both machines ---------------------------------------


@pytest.mark.parametrize("definition", [IDENTIFY, RECIPE], ids=["identify", "recipe"])
def test_every_transition_targets_a_state_that_exists(definition):
    for start_at, states in _scopes(definition):
        assert start_at in states, f"StartAt {start_at!r} is not a state"
        for name, state in states.items():
            for target in _transitions(state):
                assert target in states, f"{name} -> {target!r} does not exist in this scope"


@pytest.mark.parametrize("definition", [IDENTIFY, RECIPE], ids=["identify", "recipe"])
def test_every_state_is_reachable(definition):
    for start_at, states in _scopes(definition):
        reached = {start_at}
        frontier = [start_at]
        while frontier:
            for target in _transitions(states[frontier.pop()]):
                if target not in reached:
                    reached.add(target)
                    frontier.append(target)

        assert reached == set(states), f"unreachable: {set(states) - reached}"


@pytest.mark.parametrize("definition", [IDENTIFY, RECIPE], ids=["identify", "recipe"])
def test_every_state_terminates_or_transitions(definition):
    for _, states in _scopes(definition):
        for name, state in states.items():
            terminal = state.get("End") or state["Type"] in ("Succeed", "Fail")
            assert terminal or _transitions(state), f"{name} neither ends nor transitions"


@pytest.mark.parametrize("definition", [IDENTIFY, RECIPE], ids=["identify", "recipe"])
def test_every_resource_is_an_unresolved_placeholder(definition):
    """Function ARNs are substituted at deploy time, never hardcoded."""
    for resource in _resources(definition):
        assert resource.startswith("${") and resource.endswith("}"), resource


# --- stage 1 behaviour ------------------------------------------------------


def test_moderation_runs_first_and_alone():
    """A rejected photo must cost one moderation call and no model spend - that is
    the entire reason this state is first rather than beside the vision call."""
    assert IDENTIFY["StartAt"] == "ModerateImage"
    assert IDENTIFY["States"]["ModerateImage"]["Next"] == "IsImageAllowed"


def test_a_rejected_photo_skips_the_pipeline_and_ends_successfully():
    """Rejection is a normal outcome, not an execution failure - the job is marked
    Failed for the user, but the execution should not show as errored."""
    choice = IDENTIFY["States"]["IsImageAllowed"]
    rejected = [c for c in choice["Choices"] if c.get("BooleanEquals") is False]

    assert len(rejected) == 1
    assert rejected[0]["Variable"] == "$.moderation.allowed"
    assert rejected[0]["Next"] == "MarkJobRejected"
    assert IDENTIFY["States"]["MarkJobRejected"]["End"] is True


def test_only_an_explicit_false_verdict_blocks():
    """Fail open on 'could not check' - an unchecked verdict falls through to the
    Default, so a moderation outage does not stop the pipeline."""
    choice = IDENTIFY["States"]["IsImageAllowed"]

    assert choice["Default"] == "VisionGuess"
    assert all(c.get("BooleanEquals") is False for c in choice["Choices"])


def test_a_non_food_photo_skips_the_match_and_ends_successfully():
    """The vision guess is a food gate: a non-food photo skips restaurant lookup, the
    menu fetch and the match, and ends like a moderation rejection, not as a failure."""
    assert IDENTIFY["States"]["VisionGuess"]["Next"] == "IsFood"

    choice = IDENTIFY["States"]["IsFood"]
    not_food = [c for c in choice["Choices"] if c.get("BooleanEquals") is False]

    assert len(not_food) == 1
    assert not_food[0]["Variable"] == "$.vision.is_food"
    assert not_food[0]["Next"] == "MarkJobNotFood"
    assert choice["Default"] == "HasSelectedRestaurant"
    assert IDENTIFY["States"]["MarkJobNotFood"]["End"] is True
    # The user-facing reason comes from the vision guess.
    assert (
        IDENTIFY["States"]["MarkJobNotFood"]["Parameters"]["error_message.$"]
        == "$.vision.not_food_reason"
    )


def test_vision_gates_before_any_restaurant_or_menu_spend():
    """The food gate runs alone and first, ahead of geocode and the paid menu fetch,
    so a non-food photo triggers neither. No parallel fan-out any more."""
    states = IDENTIFY["States"]

    assert all(state["Type"] != "Parallel" for state in states.values())
    assert states["IsImageAllowed"]["Default"] == "VisionGuess"
    assert states["VisionGuess"]["Next"] == "IsFood"
    assert states["IsFood"]["Default"] == "HasSelectedRestaurant"


def test_a_selected_restaurant_skips_geocoding():
    choice = IDENTIFY["States"]["HasSelectedRestaurant"]

    assert choice["Choices"][0]["Variable"] == "$.selected_restaurant_id"
    assert choice["Choices"][0]["Next"] == "SelectRestaurantCandidate"
    assert choice["Default"] == "GeocodeRestaurantCandidates"


def test_no_candidate_skips_the_menu_fetch_but_still_matches():
    """No restaurant near those coordinates is a valid outcome - it produces the
    vision-only low-confidence match, not a failure."""
    states = IDENTIFY["States"]
    choice = states["HasCandidate"]

    assert choice["Choices"][0]["Next"] == "FetchRestaurantMenu"
    assert choice["Default"] == "NoMenu"
    # Both paths produce the same shape and flow on to the match step.
    assert states["NoMenu"]["ResultPath"] == "$.menu"
    assert states["NoMenu"]["Next"] == "MatchMenuItem"
    assert states["FetchRestaurantMenu"]["ResultPath"] == "$.menu"
    assert states["FetchRestaurantMenu"]["Next"] == "MatchMenuItem"


def test_the_match_step_receives_the_vision_guess_and_the_menu():
    params = IDENTIFY["States"]["MatchMenuItem"]["Parameters"]

    assert params["vision_guess.$"] == "$.vision"
    assert params["menu_items.$"] == "$.menu.items"
    assert params["candidate_found.$"] == "$.restaurant.candidate_found"


def test_the_vision_guess_reaches_persistence():
    """Stage 2 reads it back - nothing else records it until a recipe exists."""
    params = IDENTIFY["States"]["PersistMatchResult"]["Parameters"]

    assert params["vision_guess.$"] == "$.vision"
    assert params["match_result.$"] == "$.match"


def test_stage_one_never_generates_a_recipe():
    """The expensive generator is user-triggered - it must not run on upload."""
    resources = " ".join(_resources(IDENTIFY))

    assert "GenerateRecreation" not in resources
    assert "QueryCulinaryEmbeddings" not in resources


def test_every_failure_path_marks_the_job_failed():
    for name, state in _walk(IDENTIFY["States"]):
        for catcher in state.get("Catch", []):
            assert catcher["Next"] == "MarkJobFailed", f"{name} catches to {catcher['Next']}"
            # Preserving the input is what keeps job_id available to the handler.
            assert catcher["ResultPath"] == "$.error", name


def test_a_stage_one_failure_ends_in_a_failed_execution():
    assert IDENTIFY["States"]["MarkJobFailed"]["Next"] == "IdentifyFailed"
    assert IDENTIFY["States"]["IdentifyFailed"]["Type"] == "Fail"


# --- stage 2 behaviour ------------------------------------------------------


def test_recipe_machine_retrieves_before_generating():
    assert RECIPE["StartAt"] == "QueryCulinaryEmbeddings"
    assert RECIPE["States"]["QueryCulinaryEmbeddings"]["Next"] == "GenerateRecreation"
    assert RECIPE["States"]["GenerateRecreation"]["Next"] == "PersistRecipeResult"


def test_the_generator_is_bounded_in_time_and_retries():
    """The most expensive call in the app: a retry storm here burns the budget."""
    generate = RECIPE["States"]["GenerateRecreation"]

    assert generate["TimeoutSeconds"] > 0
    assert generate["Retry"][0]["MaxAttempts"] <= 2


def test_a_failed_generation_reverts_to_identified_not_failed():
    """Stage 1 succeeded, so the restaurant match is still good - a transient
    generator error must not discard it."""
    for name, state in _walk(RECIPE["States"]):
        for catcher in state.get("Catch", []):
            assert catcher["Next"] == "MarkRecipeFailed", name

    assert "MarkJobFailed" not in RECIPE["States"]
