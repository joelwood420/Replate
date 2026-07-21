from unittest.mock import MagicMock

from triggers import jobs_list_http


class _ConnectionCtx:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, *exc_info):
        return False


def _row(**overrides):
    defaults = dict(
        JobId="job-1",
        Status="Completed",
        IsSaved=0,
        CreatedAt=None,
        ImageBlobUrl="https://x/uploads/photo.jpg",
        DishName="Margherita Pizza",
        RestaurantName="Marchetti",
    )
    defaults.update(overrides)
    return MagicMock(**defaults)


def test_returns_empty_list_when_caller_has_no_jobs(monkeypatch):
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = []
    monkeypatch.setattr(jobs_list_http.db, "get_connection", lambda: _ConnectionCtx(conn))
    monkeypatch.setattr(jobs_list_http.blob, "generate_read_sas_url", lambda url: f"{url}?sig=abc")

    result = jobs_list_http.run("owner-oid", None, 20)

    assert result == []


def test_maps_row_fields_including_image_url_and_dish_name(monkeypatch):
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = [_row()]
    monkeypatch.setattr(jobs_list_http.db, "get_connection", lambda: _ConnectionCtx(conn))
    monkeypatch.setattr(jobs_list_http.blob, "generate_read_sas_url", lambda url: f"{url}?sig=abc")

    result = jobs_list_http.run("owner-oid", None, 20)

    assert result == [
        {
            "job_id": "job-1",
            "status": "Completed",
            "is_saved": False,
            "created_at": None,
            "dish_name": "Margherita Pizza",
            "restaurant_name": "Marchetti",
            "image_url": "https://x/uploads/photo.jpg?sig=abc",
        }
    ]


def test_scopes_query_to_caller_oid(monkeypatch):
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = []
    monkeypatch.setattr(jobs_list_http.db, "get_connection", lambda: _ConnectionCtx(conn))
    monkeypatch.setattr(jobs_list_http.blob, "generate_read_sas_url", lambda url: url)

    jobs_list_http.run("owner-oid", None, 20)

    call = conn.cursor().execute.call_args
    assert "WHERE j.UserId = ?" in call.args[0]
    assert "owner-oid" in call.args[1:]


def test_saved_filter_adds_is_saved_predicate(monkeypatch):
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = []
    monkeypatch.setattr(jobs_list_http.db, "get_connection", lambda: _ConnectionCtx(conn))
    monkeypatch.setattr(jobs_list_http.blob, "generate_read_sas_url", lambda url: url)

    jobs_list_http.run("owner-oid", True, 20)

    call = conn.cursor().execute.call_args
    assert "AND j.IsSaved = ?" in call.args[0]
    assert 1 in call.args[1:]


def test_no_saved_filter_when_not_requested(monkeypatch):
    conn = MagicMock()
    conn.cursor.return_value.fetchall.return_value = []
    monkeypatch.setattr(jobs_list_http.db, "get_connection", lambda: _ConnectionCtx(conn))
    monkeypatch.setattr(jobs_list_http.blob, "generate_read_sas_url", lambda url: url)

    jobs_list_http.run("owner-oid", None, 20)

    call = conn.cursor().execute.call_args
    assert "AND j.IsSaved = ?" not in call.args[0]


def test_parse_bool_handles_true_false_and_missing():
    assert jobs_list_http._parse_bool("true") is True
    assert jobs_list_http._parse_bool("false") is False
    assert jobs_list_http._parse_bool(None) is None
