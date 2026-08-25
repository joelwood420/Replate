"""Find a restaurant's menu page URL deterministically, via SerpApi (Google engine).

This replaces the first-party Anthropic web_search sweep that once thrashed for minutes
and over-billed (docs/decisions.md). SerpApi grounds on the restaurant name + address and
returns a real menu/website URL in a couple of seconds for ~$0.01, which the menu-fetch
step then fetches and extracts with one cheap structured Claude call - no server-side
search, no unbounded page reading.

Only the discovery half lives here (query -> best menu URL). The fetch + extract lives in
`shared/page_fetch.py` and `shared/menu_extraction.py`. A clean response that simply has no
usable URL returns None (a normal "no menu online" outcome); only a transport/HTTP/quota
failure raises SerpApiError, which the caller degrades to the vision-only outcome.
"""

import logging
from urllib.parse import urlparse

import httpx

from shared.places import OSM_USER_AGENT

SERPAPI_URL = "https://serpapi.com/search.json"

# A link whose URL or title contains one of these reads as a menu page, and is preferred over
# a bare homepage. Lower-cased substring match.
_MENU_HINTS = ("menu", "menus", "food", "carte", "dinner", "lunch", "breakfast")

# Aggregator/order sites that reliably carry full menu text when the restaurant's own site
# does not. Preferred over a generic result but below the restaurant's own menu page.
_MENU_AGGREGATORS = (
    "ubereats.com",
    "doordash.com",
    "grubhub.com",
    "menupages.com",
    "zomato.com",
    "yelp.com",
    "opentable.com",
    "seamless.com",
    "postmates.com",
    "allmenus.com",
    "tripadvisor.com",
)


class SerpApiError(Exception):
    """A SerpApi lookup failed transiently or was rejected; the caller may degrade."""


def _looks_like_menu(url: str, title: str) -> bool:
    haystack = f"{url} {title}".lower()
    return any(hint in haystack for hint in _MENU_HINTS)


def _is_aggregator(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == agg or host.endswith("." + agg) for agg in _MENU_AGGREGATORS)


def _best_url(results: dict) -> str | None:
    """Pick the single best menu URL from a SerpApi Google response.

    Preference order, most trusted first:
    1. A knowledge-graph menu link (Google's own structured menu for the place).
    2. An organic result that reads as a menu page (URL/title contains a menu hint).
    3. An organic result on a known menu aggregator (Uber Eats, DoorDash, ...).
    4. The top organic result (the restaurant's own site or best guess).
    """
    knowledge_graph = results.get("knowledge_graph") or {}
    kg_menu = knowledge_graph.get("menu")
    if isinstance(kg_menu, str) and kg_menu.startswith("http"):
        return kg_menu

    organic = results.get("organic_results") or []
    menu_like = None
    aggregator = None
    for entry in organic:
        link = entry.get("link")
        if not link or not link.startswith("http"):
            continue
        title = entry.get("title", "")
        if menu_like is None and _looks_like_menu(link, title):
            menu_like = link
        if aggregator is None and _is_aggregator(link):
            aggregator = link

    if menu_like:
        return menu_like
    if aggregator:
        return aggregator

    for entry in organic:
        link = entry.get("link")
        if link and link.startswith("http"):
            return link
    return None


def find_menu_url(name: str, address: str | None, api_key: str, timeout: float) -> str | None:
    """Return the best menu-page URL for a restaurant, or None if none is found.

    `api_key` is the SerpApi key (from SSM when deployed, an env var locally). Raises
    SerpApiError on a transport/HTTP/quota failure; returns None when the search worked but
    surfaced no usable URL (a normal outcome the caller treats as "no menu online").
    """
    query = f"{name} {address} menu" if address else f"{name} menu"
    params = {
        "engine": "google",
        "q": query,
        "num": 10,
        "api_key": api_key,
    }

    logging.info("SerpApi menu search for %s", name)
    try:
        response = httpx.get(
            SERPAPI_URL,
            params=params,
            headers={"User-Agent": OSM_USER_AGENT},
            timeout=timeout,
        )
        response.raise_for_status()
        results = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise SerpApiError(f"SerpApi lookup failed for {name}: {exc}") from exc

    # SerpApi reports a logical failure (bad key, quota exhausted) in the JSON body with a 200.
    error = results.get("error")
    if error:
        raise SerpApiError(f"SerpApi error for {name}: {error}")

    return _best_url(results)
