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


def duckduckgo_search(
    query: str,
    *,
    client: httpx.Client | None = None,
    max_results: int | None = None,
) -> list[dict]:
    """Search DuckDuckGo HTML without requiring any API keys."""
    limit = max_results or settings.web_fallback_max_results
    import urllib.parse
    owns_client = client is None
    http = client or httpx.Client(timeout=10.0)
    try:
        response = http.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query[:400]},
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"},
        )
        response.raise_for_status()
        html_content = response.text
    except Exception:
        logger.warning("duckduckgo search request failed", exc_info=True)
        return []
    finally:
        if owns_client:
            http.close()

    found: list[dict] = []
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html_content, "html.parser")
        for el in soup.select(".result"):
            a = (
                el.select_one("a.result__title")
                or el.select_one(".result__title a")
                or el.select_one("a.result__url")
                or el.select_one("a.result__snippet")
                or el.select_one("a")
            )
            if not a:
                continue
            title = a.get_text(strip=True)
            href = str(a.get("href") or "").strip()
            if "uddg=" in href:
                parsed_qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                href = parsed_qs.get("uddg", [href])[0]
            snip_el = el.select_one(".result__snippet")
            snippet = snip_el.get_text(strip=True) if snip_el else ""
            if href and (href.startswith("http://") or href.startswith("https://")):
                found.append({"url": href, "title": title or href, "description": snippet})
            if len(found) >= limit:
                break
    except Exception:
        logger.warning("duckduckgo parsing failed", exc_info=True)

    return found[:limit]


def search_web(
    query: str,
    *,
    client: httpx.Client | None = None,
    max_results: int | None = None,
) -> list[dict]:
    """Search the web using Brave if configured, otherwise fallback to DuckDuckGo."""
    limit = max_results or settings.web_fallback_max_results
    if settings.brave_api_key:
        try:
            brave_hits = brave_search(query, client=client)
            if brave_hits:
                return brave_hits[:limit]
        except Exception:
            logger.info("brave search failed, falling back to duckduckgo", exc_info=True)

    return duckduckgo_search(query, client=client, max_results=limit)


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
    except Exception:
        logger.warning("web search failed", exc_info=True)
        return WebFallback(note="Web search failed.", searched=True)

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
