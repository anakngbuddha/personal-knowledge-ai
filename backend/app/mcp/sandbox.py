"""MCP call sandbox: allowlists, SSRF, timeouts, and untrusted-result fencing."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

from app.core.config import settings
from app.core.errors import AppError, SsrfBlocked
from app.documents.injection import wrap_untrusted
from app.mcp.servers import BRAVE, MS365, PLAYWRIGHT
from app.net.ssrf import validate_url

# Original MCP tool names we will invoke. Anything else is unknown_tool.
BRAVE_ALLOWED = frozenset({"brave_web_search", "brave_news_search"})
PLAYWRIGHT_ALLOWED = frozenset(
    {
        "browser_navigate",
        "browser_snapshot",
        "browser_click",
        "browser_type",
        "browser_fill_form",
        "browser_press_key",
        "browser_navigate_back",
        "browser_wait_for",
        "browser_tabs",
    }
)
MS365_ALLOWED = frozenset(
    {
        "search_mail",
        "get_mail",
        "list_calendar",
        "search_files",
        "get_file",
        "read_excel",
        "search_contacts",
    }
)

ALLOWED_BY_SLUG = {
    BRAVE: BRAVE_ALLOWED,
    PLAYWRIGHT: PLAYWRIGHT_ALLOWED,
    MS365: MS365_ALLOWED,
}

PLAYWRIGHT_BLOCKED = frozenset(
    {
        "browser_file_upload",
        "browser_evaluate",
        "browser_run_code",
        "browser_pdf_save",
        "browser_install",
        "browser_close",
    }
)

MS365_DENY_SUBSTRINGS = (
    "send",
    "delete",
    "create",
    "update",
    "patch",
    "write",
    "upload",
    "reply",
    "forward",
    "remove",
    "move",
)


class McpSandboxError(AppError):
    def __init__(self, message: str, *, code: str = "mcp_sandbox") -> None:
        super().__init__(message, status_code=400, code=code)


def allowed_original(slug: str, original: str) -> bool:
    allowed = ALLOWED_BY_SLUG.get(slug)
    if allowed is None:
        return False
    if original in PLAYWRIGHT_BLOCKED:
        return False
    if slug == MS365:
        lowered = original.lower()
        if any(token in lowered for token in MS365_DENY_SUBSTRINGS):
            return False
    return original in allowed


def _host_permitted(host: str, allowed_hosts: tuple[str, ...] | list[str]) -> bool:
    if not allowed_hosts:
        return True
    host = (host or "").lower()
    for pattern in allowed_hosts:
        cleaned = str(pattern).lower().strip().lstrip(".")
        if not cleaned:
            continue
        if host == cleaned or host.endswith("." + cleaned):
            return True
    return False


def check_playwright_call(
    original: str,
    arguments: dict[str, Any],
    *,
    allowed_hosts: tuple[str, ...] | list[str] = (),
) -> None:
    """Reject private/metadata URLs and disallowed tab actions before the browser starts."""
    if original == "browser_tabs":
        action = str(arguments.get("action") or "list").lower()
        if action not in {"list", "select"}:
            raise McpSandboxError(f"browser_tabs action {action!r} is not allowed")

    url = arguments.get("url")
    if not url:
        if original == "browser_navigate":
            raise McpSandboxError("browser_navigate requires a url")
        return
    if not isinstance(url, str):
        raise McpSandboxError("url must be a string")

    normalized, host = validate_url(url)
    if not _host_permitted(host, allowed_hosts):
        raise SsrfBlocked(f"host {host!r} is not on the Playwright allowlist")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"}:
        raise SsrfBlocked(f"scheme {parsed.scheme!r} is not allowed")


def fence_result(payload: Any, *, source: str) -> dict[str, Any]:
    """Cap size and wrap MCP output so the LLM treats it as untrusted data."""
    if isinstance(payload, str):
        text = payload
    else:
        try:
            text = json.dumps(payload, default=str)
        except TypeError:
            text = str(payload)
    max_bytes = max(1024, int(settings.mcp_max_result_bytes))
    encoded = text.encode("utf-8")
    truncated = False
    if len(encoded) > max_bytes:
        text = encoded[:max_bytes].decode("utf-8", errors="ignore") + "...[truncated]"
        truncated = True
    return {
        "text": wrap_untrusted(text, source=source),
        "truncated": truncated,
        "untrusted": True,
    }
