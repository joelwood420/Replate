from unittest.mock import MagicMock

import httpx
import pytest

from shared import page_fetch


class _FakeStream:
    """Stand-in for the context manager httpx.stream returns."""

    def __init__(self, response=None, raise_on_enter=None):
        self._response = response
        self._raise_on_enter = raise_on_enter

    def __enter__(self):
        if self._raise_on_enter:
            raise self._raise_on_enter
        return self._response

    def __exit__(self, *args):
        return False


def _response(chunks, content_type, status_error=None, url="https://x.com/menu"):
    response = MagicMock()
    if status_error:
        response.raise_for_status.side_effect = status_error
    else:
        response.raise_for_status.return_value = None
    response.headers = {"content-type": content_type}
    response.url = url
    response.iter_bytes.return_value = iter(chunks)
    return response


def _patch_stream(monkeypatch, *, response=None, raise_on_enter=None):
    monkeypatch.setattr(
        page_fetch.httpx,
        "stream",
        lambda *a, **k: _FakeStream(response=response, raise_on_enter=raise_on_enter),
    )


def test_html_is_stripped_to_text(monkeypatch):
    html = "<html><head><style>.x{}</style></head><body><h1>Menu</h1><p>Pad Thai 13.00</p><script>x()</script></body></html>"
    _patch_stream(monkeypatch, response=_response([html.encode()], "text/html; charset=utf-8"))

    result = page_fetch.fetch_menu_content("https://x.com/menu", 10)

    assert result["kind"] == "html"
    assert "Menu" in result["text"]
    assert "Pad Thai 13.00" in result["text"]
    assert "x()" not in result["text"]
    assert ".x{}" not in result["text"]


def test_pdf_is_returned_as_bytes(monkeypatch):
    _patch_stream(monkeypatch, response=_response([b"%PDF-1.4 ", b"data"], "application/pdf"))

    result = page_fetch.fetch_menu_content("https://x.com/menu.pdf", 10)

    assert result == {"kind": "pdf", "data": b"%PDF-1.4 data", "media_type": "application/pdf"}


def test_image_is_returned_as_bytes(monkeypatch):
    _patch_stream(monkeypatch, response=_response([b"\xff\xd8\xff\xe0"], "image/jpeg"))

    result = page_fetch.fetch_menu_content("https://x.com/menu.jpg", 10)

    assert result == {"kind": "image", "data": b"\xff\xd8\xff\xe0", "media_type": "image/jpeg"}


def test_missing_content_type_is_sniffed_as_pdf(monkeypatch):
    """A PDF served with no Content-Type must not be decoded as HTML garbage."""
    _patch_stream(monkeypatch, response=_response([b"%PDF-1.7 body"], ""))

    result = page_fetch.fetch_menu_content("https://x.com/menu", 10)

    assert result["kind"] == "pdf"
    assert result["data"] == b"%PDF-1.7 body"


def test_octet_stream_image_is_sniffed(monkeypatch):
    _patch_stream(monkeypatch, response=_response([b"\x89PNG\r\n\x1a\nrest"], "application/octet-stream"))

    result = page_fetch.fetch_menu_content("https://x.com/menu", 10)

    assert result["kind"] == "image"
    assert result["media_type"] == "image/png"


def test_unknown_content_type_returns_none(monkeypatch):
    _patch_stream(monkeypatch, response=_response([b"not media"], "application/zip"))

    assert page_fetch.fetch_menu_content("https://x.com/blob", 10) is None


def test_empty_body_returns_none(monkeypatch):
    _patch_stream(monkeypatch, response=_response([], "text/html"))

    assert page_fetch.fetch_menu_content("https://x.com", 10) is None


def test_oversize_body_returns_none_without_buffering_it_all(monkeypatch):
    monkeypatch.setenv("PAGE_FETCH_MAX_BYTES", "10")
    # Streamed in chunks; the read must abort once the running total passes the cap.
    _patch_stream(monkeypatch, response=_response([b"x" * 8, b"y" * 8, b"z" * 8], "application/pdf"))

    assert page_fetch.fetch_menu_content("https://x.com/big.pdf", 10) is None


def test_transport_error_raises_page_fetch_error(monkeypatch):
    _patch_stream(monkeypatch, raise_on_enter=httpx.ConnectError("no route"))

    with pytest.raises(page_fetch.PageFetchError):
        page_fetch.fetch_menu_content("https://x.com", 10)


def test_http_status_error_raises_page_fetch_error(monkeypatch):
    err = httpx.HTTPStatusError("500", request=MagicMock(), response=MagicMock())
    _patch_stream(monkeypatch, response=_response([b"x"], "text/html", status_error=err))

    with pytest.raises(page_fetch.PageFetchError):
        page_fetch.fetch_menu_content("https://x.com", 10)


def test_blank_html_returns_none(monkeypatch):
    _patch_stream(monkeypatch, response=_response([b"<html><body></body></html>"], "text/html"))

    assert page_fetch.fetch_menu_content("https://x.com", 10) is None


def test_html_surfaces_linked_menus_food_first(monkeypatch):
    html = (
        b'<html><body><h1>Our Menus</h1>'
        b'<a href="/uploads/Kids-Menu.pdf">Kids</a>'
        b'<a href="/uploads/Drinks-Menu.pdf">Drinks</a>'
        b'<a href="/uploads/85-Set-Menu.pdf">Set Menu</a>'
        b'</body></html>'
    )
    _patch_stream(
        monkeypatch,
        response=_response([html], "text/html", url="https://baduzzi.co.nz/our-menus-2/"),
    )

    result = page_fetch.fetch_menu_content("https://baduzzi.co.nz/our-menus-2/", 10)

    assert result["kind"] == "html"
    # Relative hrefs resolved against the page URL; the food/set menu ranks above drinks/kids.
    assert result["menu_links"][0] == "https://baduzzi.co.nz/uploads/85-Set-Menu.pdf"
    assert "https://baduzzi.co.nz/uploads/Drinks-Menu.pdf" in result["menu_links"]
    assert "https://baduzzi.co.nz/uploads/Kids-Menu.pdf" in result["menu_links"]


def test_surfaces_a_same_host_menu_page_at_an_extensionless_url(monkeypatch):
    """The a-la-carte case: a same-host page whose PATH reads as a menu (e.g. /menu1-2/, which
    actually serves a PDF) is surfaced even without a .pdf extension. The page itself and API
    links whose menu word is only in the query are excluded."""
    html = (
        b'<html><body>'
        b'<a href="/our-menus-2/">Menus</a>'                      # the page itself - excluded
        b'<a href="/wp-json/oembed/1.0/embed?url=/our-menus-2/">oembed</a>'  # menu only in query
        b'<a href="/menu1-2/">A la carte</a>'                     # extensionless menu page - kept
        b'<a href="https://facebook.com/baduzzi">Facebook</a>'    # off-site, not a menu - excluded
        b'</body></html>'
    )
    _patch_stream(
        monkeypatch,
        response=_response([html], "text/html", url="https://baduzzi.co.nz/our-menus-2/"),
    )

    result = page_fetch.fetch_menu_content("https://baduzzi.co.nz/our-menus-2/", 10)

    assert result["menu_links"] == ["https://baduzzi.co.nz/menu1-2/"]


def test_a_landing_page_with_no_text_but_menu_links_is_kept(monkeypatch):
    """No readable dishes, but it links a menu - exactly the page to follow, not drop."""
    html = b'<html><body><a href="https://cdn.example.com/food-menu.pdf"></a></body></html>'
    _patch_stream(monkeypatch, response=_response([html], "text/html", url="https://x.com/menu"))

    result = page_fetch.fetch_menu_content("https://x.com/menu", 10)

    assert result is not None
    # A .pdf link is followed even cross-host (menus are sometimes on a CDN).
    assert result["menu_links"] == ["https://cdn.example.com/food-menu.pdf"]


def test_html_without_menu_links_has_an_empty_list(monkeypatch):
    _patch_stream(monkeypatch, response=_response([b"<html><body>Pad Thai 13.00</body></html>"], "text/html"))

    result = page_fetch.fetch_menu_content("https://x.com/menu", 10)

    assert result["menu_links"] == []
