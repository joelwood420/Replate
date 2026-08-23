from shared import repository
from triggers import profile_http


def test_get_creates_profile_lazily_for_a_new_user(ddb_table):
    result = profile_http.get_run("new-oid")

    assert result["status_code"] == 200
    assert result["body"] == {"display_name": None, "email": None, "created_at": result["body"]["created_at"]}
    assert result["body"]["created_at"] is not None


def test_get_returns_stored_fields(ddb_table):
    repository.ensure_user("oid-1", email="cook@example.com", display_name="Amara")

    result = profile_http.get_run("oid-1")

    assert result["status_code"] == 200
    assert result["body"]["display_name"] == "Amara"
    assert result["body"]["email"] == "cook@example.com"


def test_update_sets_display_name_and_persists(ddb_table):
    result = profile_http.update_run("oid-1", "Amara Silva")

    assert result["status_code"] == 200
    assert result["body"]["display_name"] == "Amara Silva"
    assert repository.get_profile("oid-1")["display_name"] == "Amara Silva"


def test_update_trims_surrounding_whitespace(ddb_table):
    result = profile_http.update_run("oid-1", "  Amara  ")

    assert result["status_code"] == 200
    assert result["body"]["display_name"] == "Amara"


def test_update_preserves_email_across_the_change(ddb_table):
    repository.ensure_user("oid-1", email="cook@example.com", display_name="Old")

    profile_http.update_run("oid-1", "New Name")

    profile = repository.get_profile("oid-1")
    assert profile["display_name"] == "New Name"
    assert profile["email"] == "cook@example.com"


def test_update_rejects_empty_name(ddb_table):
    result = profile_http.update_run("oid-1", "   ")

    assert result["status_code"] == 400
    # Nothing was written.
    assert repository.get_profile("oid-1")["display_name"] is None


def test_update_rejects_a_too_long_name(ddb_table):
    result = profile_http.update_run("oid-1", "x" * 81)

    assert result["status_code"] == 400
    assert repository.get_profile("oid-1")["display_name"] is None


def test_update_rejects_a_non_string(ddb_table):
    result = profile_http.update_run("oid-1", None)

    assert result["status_code"] == 400
