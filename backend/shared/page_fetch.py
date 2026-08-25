"""Fetch a menu page and return it in a form the extract step can hand to Claude.

A restaurant menu is as often a PDF or an image scan as it is an HTML page, so this returns
a tagged result rather than plain text: HTML is stripped to text, a PDF or image is returned
as raw bytes + media type so `menu_extraction` can pass it to the model as a document/image
content block (Claude reads both natively). Handling those, not just HTML, is the main
menu-hit-rate lever.

Two failure modes are kept distinct, so a transient blip is not cached as a permanent
answer:
- A **transport/HTTP error** raises `PageFetchError` - the caller degrades but does NOT cache,
  so the next job retries (matching how a SerpApi error is handled).
- A genuine "**nothing usable here**" - an unknown content type, an empty body, or a download
  over the size cap - returns `None`, which the caller treats as "no menu at this URL" and may
  cache. This is a real answer, not a blip.

The body is streamed and abandoned the moment it crosses the byte cap, so a huge PDF/image
cannot be fully buffered into the Lambda's memory before being rejected.
"""

import logging
import re
from urllib.parse import urljoin, urlparse

import httpx

from shared import config
from shared.places import OSM_USER_AGENT

# Strip <script>/<style> blocks whole, then all remaining tags, so menu text survives without
# a heavy HTML parser dependency.
_SCRIPT_STYLE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"[ \t\r\f\v]+")
_BLANK_LINES = re.compile(r"\n\s*\n+")

# Links from an HTML page. Many restaurant "menu" pages are a shell that links the real menus
# as separate PDFs or sub-pages - sometimes at pretty, extensionless URLs that still serve a
# PDF (e.g. /menu1-2/ returning application/pdf). So a menu link is either a .pdf href OR a
# same-host page whose PATH reads as a menu; page_fetch sorts out PDF-vs-HTML per target.
_HREF = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
# Matched against the URL PATH only, so API links like /wp-json/oembed?url=...menu... are excluded.
_MENU_PATH_HINTS = ("menu", "food", "dinner", "lunch", "breakfast", "carte", "mains")
_FOOD_HINTS = ("menu", "food", "dinner", "lunch", "breakfast", "set-menu", "set_menu", "a-la-carte", "carte", "main")
_NEGATIVE_HINTS = ("drink", "wine", "bar", "kids", "child", "dessert", "cocktail", "beverage")
# Cap how many candidate links we surface; the caller follows only a few, so more is noise.
_MAX_MENU_LINKS = 8


def _menu_link_score(url: str) -> int:
    low = url.lower()
    value = 0
    if any(hint in low for hint in _FOOD_HINTS):
        value += 2
    if any(hint in low for hint in _NEGATIVE_HINTS):
        value -= 2
    return value


def _find_menu_links(html: str, base_url: str) -> list[str]:
    """Absolute URLs of menus linked from an HTML page, most menu-like first.

    A candidate is either a `.pdf` href (any host) or a same-host page whose PATH contains a
    menu word - the latter catches menus served at extensionless URLs. The page we are already
    on is excluded. Ranks food/menu above drinks/kids so the caller (which follows only a few)
    spends its budget on the mains, not the wine list. Relative hrefs are resolved against the
    page URL; ties keep page order (Python's sort is stable).
    """
    base = urlparse(base_url)
    base_key = (base.netloc, base.path.rstrip("/"))
    seen: set[tuple] = set()
    links: list[str] = []
    for href in _HREF.findall(html):
        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https"):
            continue
        low_path = parsed.path.lower()
        is_pdf = low_path.endswith(".pdf")
        is_menu_page = parsed.netloc == base.netloc and any(h in low_path for h in _MENU_PATH_HINTS)
        if not (is_pdf or is_menu_page):
            continue
        if (parsed.netloc, parsed.path.rstrip("/")) == base_key:
            continue  # the page we're already on
        key = (parsed.netloc, parsed.path.rstrip("/"), parsed.query)
        if key in seen:
            continue
        seen.add(key)
        links.append(absolute)

    links.sort(key=_menu_link_score, reverse=True)
    return links[:_MAX_MENU_LINKS]


class PageFetchError(Exception):
    """The menu page could not be fetched transiently (transport/HTTP error); retry later."""


def _strip_html(raw: str) -> str:
    text = _SCRIPT_STYLE.sub(" ", raw)
    text = _TAG.sub(" ", text)
    # Collapse the whitespace the tag removal leaves behind, but keep line breaks so item
    # names and prices do not run together into one wall of text.
    text = _WHITESPACE.sub(" ", text)
    text = _BLANK_LINES.sub("\n", text)
    return text.strip()


def _sniff_media_type(body: bytes) -> str | None:
    """Identify a PDF or image from its leading bytes, for servers that send no Content-Type."""
    if body.startswith(b"%PDF"):
        return "application/pdf"
    if body.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if body.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if body[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return "image/webp"
    return None


def _read_capped(response: httpx.Response, max_bytes: int) -> bytes | None:
    """Read the streamed body, stopping (returning None) the moment it exceeds max_bytes."""
    chunks = []
    total = 0
    for chunk in response.iter_bytes():
        total += len(chunk)
        if total > max_bytes:
            return None
        chunks.append(chunk)
    return b"".join(chunks)


def fetch_menu_content(url: str, timeout: float) -> dict | None:
    """Fetch `url` and return a tagged content dict, or None if it yields no usable menu.

    Return shapes:
    - {"kind": "html",  "text": <plain text>, "menu_links": [<url>, ...]}
    - {"kind": "pdf",   "data": <bytes>, "media_type": "application/pdf"}
    - {"kind": "image", "data": <bytes>, "media_type": "image/..."}

    Returns None for an unknown content type, an empty body, or an over-cap download (genuine
    "nothing usable" - the caller may cache it). Raises PageFetchError on a transport/HTTP error
    (transient - the caller degrades without caching).
    """
    max_bytes = config.page_fetch_max_bytes()
    try:
        with httpx.stream(
            "GET",
            url,
            headers={"User-Agent": OSM_USER_AGENT},
            timeout=timeout,
            follow_redirects=True,
        ) as response:
            response.raise_for_status()
            # Content-Type can carry a charset/parameters, so match on the bare media type.
            content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
            final_url = str(response.url)
            body = _read_capped(response, max_bytes)
    except httpx.HTTPError as exc:
        raise PageFetchError(f"could not fetch {url}: {exc}") from exc

    if body is None:
        logging.info("Menu page for %s exceeded the %d-byte cap; skipping", url, max_bytes)
        return None
    if not body:
        return None

    # A server that sends no (or a generic) Content-Type on a real PDF/image would otherwise be
    # decoded as HTML and feed binary garbage to the model. Sniff the leading bytes to recover.
    if not content_type or content_type == "application/octet-stream":
        content_type = _sniff_media_type(body) or content_type

    if content_type == "application/pdf":
        return {"kind": "pdf", "data": body, "media_type": "application/pdf"}
    if content_type in ("image/jpeg", "image/png", "image/gif", "image/webp"):
        return {"kind": "image", "data": body, "media_type": content_type}
    if content_type.startswith("text/") or content_type in ("application/xhtml+xml", ""):
        html = body.decode("utf-8", "replace")
        text = _strip_html(html)
        menu_links = _find_menu_links(html, final_url)
        # Keep the page even when it has no readable text, as long as it links to menus - a
        # landing page whose real menus are all separate files/pages is exactly what to follow.
        if not text and not menu_links:
            return None
        return {"kind": "html", "text": text, "menu_links": menu_links}

    logging.info("Menu page for %s has unsupported content-type %r", url, content_type)
    return None
