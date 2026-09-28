"""Web fallback when the knowledge base has nothing useful.

Tavily or Brave Search finds pages. The SSRF-safe fetcher reads them. Playwright stays
off this path so a miss does not open a browser.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser

import httpx

from app.core.config import settings
from app.core.errors import SsrfBlocked
from app.core.logging import get_logger
from app.net.ssrf import ROBOTS_PRODUCT_TOKEN, fetch, fetch_robots

logger = get_logger(__name__)

BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
TAVILY_ENDPOINT = "https://api.tavily.com/search"
_SKIP_TAGS = frozenset({"script", "style", "noscript", "svg"})


@dataclass(frozen=True)
class WebPassage:
    url: str
    title: str
    text: str


@dataclass
class WebFallback:
    passages: list[WebPassage] = field(default_factory=list)
    note: str | None = None
    searched: bool = False


class WebSearchUnavailable(Exception):
    """A configured search provider could not return results."""


def tavily_search(query: str, *, client: httpx.Client | None = None, max_results: int | None = None) -> list[dict]:
    """Use Tavily's basic search without its generated answer or paid extraction."""
    limit = max_results or settings.web_fallback_max_results
    owns_client = client is None
    http = client or httpx.Client(timeout=8.0)
    try:
        response = http.post(
            TAVILY_ENDPOINT,
            headers={"Authorization": f"Bearer {settings.tavily_api_key}"},
            json={"query": query[:400], "search_depth": "basic", "max_results": limit,
                  "include_answer": False, "include_raw_content": False},
        )
        response.raise_for_status()
        payload = response.json()
    finally:
        if owns_client:
            http.close()
    return [
        {"url": str(item["url"]), "title": str(item.get("title") or item["url"]),
         "description": str(item.get("content") or "")}
        for item in (payload.get("results") or [])[:limit]
        if isinstance(item, dict) and item.get("url")
    ]


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() in _SKIP_TAGS:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag.lower() in _SKIP_TAGS and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if self._skip:
            return
        text = " ".join(data.split())
        if text:
            self.parts.append(text)


def html_to_text(data: bytes, *, limit: int) -> str:
    parser = _TextExtractor()
    parser.feed(data.decode("utf-8", errors="replace"))
    return " ".join(parser.parts)[:limit].strip()


def brave_search(query: str, *, client: httpx.Client | None = None) -> list[dict]:
    """Return Brave web results as title/url/description dicts."""
    if not settings.brave_api_key:
        return []
    params = {"q": query[:400], "count": settings.web_fallback_max_results}
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": settings.brave_api_key,
    }
    owns_client = client is None
    http = client or httpx.Client(timeout=10.0)
    try:
        response = http.get(BRAVE_ENDPOINT, params=params, headers=headers)
        response.raise_for_status()
        payload = response.json()
    finally:
        if owns_client:
            http.close()
    results = ((payload.get("web") or {}).get("results") or []) if isinstance(payload, dict) else []
    found: list[dict] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        found.append(
            {
                "url": url,
                "title": str(item.get("title") or url),
                "description": str(item.get("description") or ""),
            }
        )
    return found[: settings.web_fallback_max_results]


def search_web(
    query: str,
    *,
    client: httpx.Client | None = None,
    max_results: int | None = None,
) -> list[dict]:
    """Search with a configured API; HTML scraping is too unreliable for answers."""
    limit = max_results or settings.web_fallback_max_results
    if settings.tavily_api_key:
        return tavily_search(query, client=client, max_results=limit)
    if settings.brave_api_key:
        return brave_search(query, client=client)[:limit]
    raise WebSearchUnavailable("Web search is not configured. Add a free Tavily API key.")


def gather_web_fallback(
    query: str,
    *,
    search_fn=None,
    fetch_fn=None,
    robots_fn=None,
    force: bool = False,
) -> WebFallback:
    """Search, then read the top pages that robots.txt and SSRF allow."""
    lookup = search_fn or search_web
    try:
        hits = list(lookup(query) or [])
    except WebSearchUnavailable as exc:
        return WebFallback(note=str(exc), searched=False)
    except httpx.HTTPStatusError as exc:
        logger.warning("web search provider returned HTTP %s", exc.response.status_code)
        note = "Web search quota or rate limit reached." if exc.response.status_code in {429, 432, 433} else "Web search provider is unavailable."
        return WebFallback(note=note, searched=False)
    except httpx.TimeoutException:
        logger.warning("web search provider timed out")
        return WebFallback(note="Web search timed out. Please try again.", searched=False)
    except Exception:
        logger.warning("web search failed", exc_info=True)
        return WebFallback(note="Web search is unavailable. Please try again.", searched=False)

    if not hits:
        return WebFallback(note="No matching web results found.", searched=True)

    fetch_page = fetch_fn or fetch
    robots_for = robots_fn or fetch_robots
    passages: list[WebPassage] = []
    for hit in hits[: settings.web_fallback_max_results]:
        url = str(hit.get("url") or "").strip()
        title = str(hit.get("title") or url)
        if not url:
            continue
        try:
            rules = robots_for(url)
            if rules is not None and not rules.allows(url, ROBOTS_PRODUCT_TOKEN):
                continue
            resource = fetch_page(url)
        except SsrfBlocked:
            logger.info("skipped SSRF-blocked web result %s", url)
            continue
        except Exception:
            logger.info("skipped unreadable web result %s, fallback to snippet", url)
            desc = str(hit.get("description") or "").strip()
            if desc:
                passages.append(WebPassage(url=url, title=title, text=desc))
            continue
        body = getattr(resource, "data", b"") or b""
        content_type = (getattr(resource, "content_type", None) or "").lower()
        if "html" in content_type or body.lstrip().startswith(b"<"):
            text = html_to_text(body, limit=settings.web_fallback_max_chars)
        else:
            text = body.decode("utf-8", errors="replace")[: settings.web_fallback_max_chars].strip()
        if not text:
            text = str(hit.get("description") or "").strip()
        if not text:
            continue
        final_url = getattr(resource, "final_url", None) or url
        passages.append(WebPassage(url=final_url, title=title, text=text))
    return WebFallback(passages=passages, searched=True)
