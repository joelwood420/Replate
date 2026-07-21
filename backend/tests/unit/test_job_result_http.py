from unittest.mock import MagicMock

from triggers import job_result_http
from shared.models import JobStatus


class _ConnectionCtx:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, *exc_info):
        return False


def test_returns_404_for_unknown_job_id(monkeypatch):
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = None
    monkeypatch.setattr(job_result_http.db, "get_connection", lambda: _ConnectionCtx(conn))

    result = job_result_http.run("missing-job", "user-oid-1")

    assert result["status_code"] == 404


def test_returns_403_when_oid_does_not_match_job_owner(monkeypatch):
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = MagicMock(
        JobId="job-1",
        UserId="owner-oid",
        Status=JobStatus.PROCESSING,
        ErrorMessage=None,
        ImageBlobUrl="https://x/uploads/photo.jpg",
        IsSaved=0,
    )
    monkeypatch.setattr(job_result_http.db, "get_connection", lambda: _ConnectionCtx(conn))
    monkeypatch.setattr(job_result_http.blob, "generate_read_sas_url", lambda url: f"{url}?sig=abc")

    result = job_result_http.run("job-1", "different-oid")

    assert result["status_code"] == 403


def test_returns_pending_status_when_not_yet_completed(monkeypatch):
    conn = MagicMock()
    conn.cursor.return_value.fetchone.return_value = MagicMock(
        JobId="job-1",
        UserId="owner-oid",
        Status=JobStatus.PROCESSING,
        ErrorMessage=None,
        ImageBlobUrl="https://x/uploads/photo.jpg",
        IsSaved=0,
    )
    monkeypatch.setattr(job_result_http.db, "get_connection", lambda: _ConnectionCtx(conn))
    monkeypatch.setattr(job_result_http.blob, "generate_read_sas_url", lambda url: f"{url}?sig=abc")

    result = job_result_http.run("job-1", "owner-oid")

    assert result["status_code"] == 200
    assert result["body"]["status"] == JobStatus.PROCESSING
    assert result["body"]["image_url"] == "https://x/uploads/photo.jpg?sig=abc"
    assert result["body"]["is_saved"] is False
    assert "result" not in result["body"]


def test_returns_full_nested_result_when_completed(monkeypatch):
    conn = MagicMock()
    cursor = conn.cursor.return_value
    job_row = MagicMock(
        JobId="job-1",
        UserId="owner-oid",
        Status=JobStatus.COMPLETED,
        ErrorMessage=None,
        ImageBlobUrl="https://x/uploads/photo.jpg",
        IsSaved=1,
    )
    result_row = MagicMock(
        DishName="Margherita Pizza",
        Cuisine="Italian",
        Confidence=0.8,
        MatchedRestaurantId="stub-1",
        MatchedMenuItemId=None,
        MatchConfidence=0.9,
        MatchMethod="menu_matched",
    )
    element_row = MagicMock(ElementId="el-1", Name="Crust", Description="desc", Role="Base")

    cursor.fetchone.side_effect = [job_row, result_row]
    cursor.fetchall.side_effect = [[element_row], [], []]

    monkeypatch.setattr(job_result_http.db, "get_connection", lambda: _ConnectionCtx(conn))
    monkeypatch.setattr(job_result_http.blob, "generate_read_sas_url", lambda url: f"{url}?sig=abc")

    result = job_result_http.run("job-1", "owner-oid")

    assert result["status_code"] == 200
    assert result["body"]["image_url"] == "https://x/uploads/photo.jpg?sig=abc"
    assert result["body"]["is_saved"] is True
    assert result["body"]["result"]["dish_name"] == "Margherita Pizza"
    assert len(result["body"]["result"]["elements"]) == 1
    assert result["body"]["result"]["elements"][0]["name"] == "Crust"
    assert result["body"]["result"]["elements"][0]["role"] == "Base"
