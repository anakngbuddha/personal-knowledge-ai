"""Web fallback when the knowledge base has nothing useful.

Brave Search finds pages. The SSRF-safe fetcher reads them. Playwright stays
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


def gather_web_fallback(
    query: str,
    *,
    search_fn=None,
    fetch_fn=None,
    robots_fn=None,
) -> WebFallback:
    """Search, then read the top pages that robots.txt and SSRF allow."""
    if not settings.brave_api_key and search_fn is None:
        return WebFallback(note="Web search is not configured.")

    lookup = search_fn or brave_search
    try:
        hits = list(lookup(query) or [])
    except Exception:
        logger.warning("web search failed", exc_info=True)
        return WebFallback(note="Web search failed.", searched=True)

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
            logger.info("skipped blocked web result %s", url)
            continue
        except Exception:
            logger.info("skipped unreadable web result %s", url, exc_info=True)
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
