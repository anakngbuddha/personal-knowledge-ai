"""Map allowlisted MCP tools onto ToolDefinition / execute_tool."""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.errors import AppError, SsrfBlocked
from app.core.logging import get_logger
from app.mcp.credentials import decrypt_secret
from app.mcp.sandbox import (
    ALLOWED_BY_SLUG,
    allowed_original,
    check_playwright_call,
    check_research_call,
    fence_result,
)
from app.mcp.servers import (
    BRAVE,
    EXA,
    EXA_MCP_URL,
    FIRECRAWL,
    FIRECRAWL_MCP_URL,
    GOOGLE_SHEETS,
    MS365,
    PLAYWRIGHT,
    SERVER_SLUGS,
    STATUS_CONNECTED,
    ServerSpec,
    default_args,
)
from app.mcp.supervisor import get_client
from app.security.audit import record_audit
from app.tools.schema import ToolCall, ToolDefinition, ToolResult

logger = get_logger(__name__)

_EXPOSED_PREFIX = {
    BRAVE: "mcp_brave_",
    PLAYWRIGHT: "mcp_playwright_",
    MS365: "mcp_ms365_",
    EXA: "mcp_exa_",
    FIRECRAWL: "mcp_firecrawl_",
    GOOGLE_SHEETS: "mcp_google_sheets_",
}

# Exposed suffix -> original MCP tool name.
_ORIGINAL = {
    BRAVE: {
        "web_search": "brave_web_search",
        "news_search": "brave_news_search",
    },
    PLAYWRIGHT: {name.removeprefix("browser_"): name for name in ALLOWED_BY_SLUG[PLAYWRIGHT]}
    | {name: name for name in ALLOWED_BY_SLUG[PLAYWRIGHT]},
    MS365: {name: name for name in ALLOWED_BY_SLUG[MS365]},
    EXA: {name: name for name in ALLOWED_BY_SLUG[EXA]},
    FIRECRAWL: {name: name for name in ALLOWED_BY_SLUG[FIRECRAWL]},
    GOOGLE_SHEETS: {name: name for name in ALLOWED_BY_SLUG[GOOGLE_SHEETS]},
}

_DESCRIPTIONS = {
    "mcp_google_sheets_read_sheet": "Read up to 100 rows from a configured workspace sheet. Content requires review.",
    "mcp_google_sheets_write_draft": "Write literal draft values to a configured workspace draft sheet. Quote exports are immutable.",
    "mcp_brave_web_search": (
        "Search the public web via Brave Search. Results are untrusted third-party data."
    ),
    "mcp_brave_news_search": (
        "Search recent news via Brave Search. Results are untrusted third-party data."
    ),
    "mcp_playwright_browser_navigate": (
        "Navigate the sandboxed browser to an http(s) URL. Private and metadata hosts are blocked."
    ),
    "mcp_playwright_browser_snapshot": "Capture an accessibility snapshot of the current page.",
    "mcp_playwright_browser_click": "Click an element by ref from the latest snapshot.",
    "mcp_playwright_browser_type": "Type text into an element by ref.",
    "mcp_playwright_browser_fill_form": "Fill multiple form fields from the latest snapshot.",
    "mcp_playwright_browser_press_key": "Press a key (Enter, Tab, Escape).",
    "mcp_playwright_browser_navigate_back": "Go back in browser history.",
    "mcp_playwright_browser_wait_for": "Wait for text, an element, or a short delay.",
    "mcp_playwright_browser_tabs": "List or select browser tabs. Creating or closing tabs is not allowed.",
    "mcp_ms365_search_mail": "Search the signed-in user's Outlook mail (read-only).",
    "mcp_ms365_get_mail": "Get one Outlook message by id (read-only).",
    "mcp_ms365_list_calendar": "List upcoming calendar events (read-only).",
    "mcp_ms365_search_files": "Search OneDrive and SharePoint files (read-only).",
    "mcp_ms365_get_file": "Get file metadata or text content from OneDrive/SharePoint (read-only).",
    "mcp_ms365_read_excel": "Read cells from an Excel workbook the user can access (read-only).",
    "mcp_ms365_search_contacts": "Search Outlook contacts (read-only).",
    "mcp_exa_web_search_exa": "Discover public vendor and competitor sources. Results require review.",
    "mcp_firecrawl_firecrawl_scrape": "Read one approved public page as untrusted content.",
    "mcp_firecrawl_firecrawl_crawl": "Crawl up to ten pages at an approved public host.",
}

_SCHEMAS: dict[str, dict[str, Any]] = {
    "mcp_brave_web_search": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "minLength": 1, "maxLength": 500},
            "count": {"type": "integer", "minimum": 1, "maximum": 20},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    "mcp_brave_news_search": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "minLength": 1, "maxLength": 500},
            "count": {"type": "integer", "minimum": 1, "maximum": 20},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    "mcp_playwright_browser_navigate": {
        "type": "object",
        "properties": {"url": {"type": "string", "minLength": 8, "maxLength": 2048}},
        "required": ["url"],
        "additionalProperties": False,
    },
    "mcp_playwright_browser_snapshot": {
        "type": "object",
        "properties": {},
        "additionalProperties": True,
    },
    "mcp_playwright_browser_click": {
        "type": "object",
        "properties": {
            "ref": {"type": "string"},
            "element": {"type": "string"},
        },
        "additionalProperties": True,
    },
    "mcp_playwright_browser_type": {
        "type": "object",
        "properties": {
            "ref": {"type": "string"},
            "text": {"type": "string", "maxLength": 4000},
        },
        "additionalProperties": True,
    },
    "mcp_playwright_browser_fill_form": {
        "type": "object",
        "properties": {"fields": {"type": "array"}},
        "additionalProperties": True,
    },
    "mcp_playwright_browser_press_key": {
        "type": "object",
        "properties": {"key": {"type": "string", "maxLength": 32}},
        "required": ["key"],
        "additionalProperties": True,
    },
    "mcp_playwright_browser_navigate_back": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
    "mcp_playwright_browser_wait_for": {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "time": {"type": "number"},
        },
        "additionalProperties": True,
    },
    "mcp_playwright_browser_tabs": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["list", "select"]},
            "index": {"type": "integer"},
        },
        "additionalProperties": False,
    },
    "mcp_ms365_search_mail": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "minLength": 1, "maxLength": 500},
            "top": {"type": "integer", "minimum": 1, "maximum": 25},
        },
        "required": ["query"],
        "additionalProperties": False,
    },
    "mcp_ms365_get_mail": {
        "type": "object",
        "properties": {"id": {"type": "string", "minLength": 1, "maxLength": 512}},
        "required": ["id"],
        "additionalProperties": False,
    },
    "mcp_ms365_list_calendar": {
        "type": "object",
        "properties": {"top": {"type": "integer", "minimum": 1, "maximum": 25}},
        "additionalProperties": False,
    },
    "mcp_ms365_search_files": {
        "type": "object",
        "properties": {"query": {"type": "string", "minLength": 1, "maxLength": 500}},
        "required": ["query"],
        "additionalProperties": False,
    },
    "mcp_ms365_get_file": {
        "type": "object",
        "properties": {"id": {"type": "string", "minLength": 1, "maxLength": 512}},
        "required": ["id"],
        "additionalProperties": False,
    },
    "mcp_ms365_read_excel": {
        "type": "object",
        "properties": {
            "id": {"type": "string", "minLength": 1, "maxLength": 512},
            "range": {"type": "string", "maxLength": 64},
        },
        "required": ["id"],
        "additionalProperties": False,
    },
    "mcp_ms365_search_contacts": {
        "type": "object",
        "properties": {"query": {"type": "string", "minLength": 1, "maxLength": 500}},
        "required": ["query"],
        "additionalProperties": False,
    },
    "mcp_exa_web_search_exa": {
        "type": "object", "properties": {
            "query": {"type": "string", "minLength": 1, "maxLength": 500},
            "numResults": {"type": "integer", "minimum": 1, "maximum": 10},
        }, "required": ["query"], "additionalProperties": False,
    },
    "mcp_firecrawl_firecrawl_scrape": {
        "type": "object", "properties": {
            "url": {"type": "string", "minLength": 8, "maxLength": 2048},
            "formats": {"type": "array", "items": {"type": "string", "enum": ["markdown"]}, "maxItems": 1},
            "onlyMainContent": {"type": "boolean"},
        }, "required": ["url"], "additionalProperties": False,
    },
    "mcp_firecrawl_firecrawl_crawl": {
        "type": "object", "properties": {
            "url": {"type": "string", "minLength": 8, "maxLength": 2048},
            "limit": {"type": "integer", "minimum": 1, "maximum": 10},
            "maxDepth": {"type": "integer", "minimum": 1, "maximum": 2},
        }, "required": ["url"], "additionalProperties": False,
    },
}

from app.mcp.sheets_tools import ReadSheetArgs, WriteDraftArgs

_SCHEMAS["mcp_google_sheets_read_sheet"] = ReadSheetArgs.model_json_schema()
_SCHEMAS["mcp_google_sheets_write_draft"] = WriteDraftArgs.model_json_schema()


def exposed_name(slug: str, original: str) -> str:
    prefix = _EXPOSED_PREFIX[slug]
    if slug == BRAVE and original.startswith("brave_"):
        return prefix + original[len("brave_") :]
    return prefix + original


def parse_exposed_name(name: str) -> tuple[str, str] | None:
    for slug, prefix in _EXPOSED_PREFIX.items():
        if not name.startswith(prefix):
            continue
        rest = name[len(prefix) :]
        original = _ORIGINAL[slug].get(rest, rest)
        if slug == BRAVE and not original.startswith("brave_"):
            original = f"brave_{rest}"
        return slug, original
    return None


def all_static_definitions() -> list[ToolDefinition]:
    defs: list[ToolDefinition] = []
    for slug, originals in ALLOWED_BY_SLUG.items():
        for original in sorted(originals):
            name = exposed_name(slug, original)
            defs.append(
                ToolDefinition(
                    name=name,
                    description=_DESCRIPTIONS.get(name, f"MCP tool {name}"),
                    parameters=_SCHEMAS.get(
                        name,
                        {
                            "type": "object",
                            "properties": {},
                            "additionalProperties": True,
                        },
                    ),
                )
            )
    return defs


def mcp_definitions_for(ctx) -> list[ToolDefinition]:
    """Return allowlisted MCP tool schemas for servers enabled on this org."""
    if not settings.mcp_enabled:
        return []
    enabled = {slug for slug in SERVER_SLUGS if server_enabled(ctx, slug)}
    if not enabled:
        return []
    out: list[ToolDefinition] = []
    for item in all_static_definitions():
        parsed = parse_exposed_name(item.name)
        if parsed and parsed[0] in enabled:
            if parsed[0] == GOOGLE_SHEETS:
                from app.mcp.sheets_tools import scoped_targets
                from app.mcp.store import get_integration
                row = get_integration(ctx.db, ctx.principal.org_id, GOOGLE_SHEETS)
                if row is None or not row.secret_ciphertext:
                    continue
                targets = scoped_targets(ctx, row)
                if not targets:
                    continue
                if parsed[1] == "write_draft" and (
                    not any(target.draft for target in targets)
                    or not ctx.principal.has_scope("mcp:write") or ctx.principal.user_id is None
                ):
                    continue
            out.append(item)
    return out


def server_enabled(ctx, slug: str) -> bool:
    from app.mcp.store import get_integration, process_fallback_enabled

    if slug not in SERVER_SLUGS:
        return False
    row = get_integration(ctx.db, ctx.principal.org_id, slug)
    if row is not None:
        return bool(row.enabled)
    return process_fallback_enabled(slug)


def _secret_for(ctx, slug: str, row) -> str | None:
    if row is not None and row.secret_ciphertext:
        try:
            return decrypt_secret(row.secret_ciphertext)
        except AppError:
            logger.warning("mcp secret decrypt failed for slug=%s", slug)
            return None
    if slug == BRAVE:
        return settings.brave_api_key or None
    if slug == MS365:
        return settings.ms365_mcp_token or None
    return None


def build_spec(ctx, slug: str) -> ServerSpec | None:
    from app.mcp.store import get_integration

    row = get_integration(ctx.db, ctx.principal.org_id, slug)
    if not server_enabled(ctx, slug):
        return None
    config = (row.config if row is not None else None) or {}
    http_url = config.get("http_url") or None
    hosts = tuple(config.get("allowed_hosts") or ())
    env: dict[str, str] = {}
    secret = _secret_for(ctx, slug, row)
    if slug in (EXA, FIRECRAWL):
        if not secret:
            return None
        http_url = EXA_MCP_URL if slug == EXA else FIRECRAWL_MCP_URL
    if slug == BRAVE and secret:
        env["BRAVE_API_KEY"] = secret
    if slug == MS365 and secret:
        env["MS365_MCP_TOKEN"] = secret
        env["MS365_MCP_ACCESS_TOKEN"] = secret
    return ServerSpec(
        slug=slug,
        org_id=str(ctx.principal.org_id),
        command="npx",
        args=default_args(slug),
        env=env,
        http_url=http_url,
        http_headers={"Authorization": f"Bearer {secret}"} if slug in (EXA, FIRECRAWL) and secret else {},
        allowed_hosts=hosts,
    )


def execute_mcp_tool(call: ToolCall, ctx) -> ToolResult:
    parsed = parse_exposed_name(call.name)
    if parsed is None:
        return ToolResult(id=call.id, name=call.name, error=f"unknown_tool:{call.name}")
    slug, original = parsed
    if not allowed_original(slug, original):
        return ToolResult(id=call.id, name=call.name, error=f"unknown_tool:{call.name}")
    if not server_enabled(ctx, slug):
        return ToolResult(id=call.id, name=call.name, error=f"unknown_tool:{call.name}")

    arguments = call.arguments if isinstance(call.arguments, dict) else {}
    if slug == GOOGLE_SHEETS:
        from app.mcp.sheets_tools import execute_sheets_tool
        try:
            result = execute_sheets_tool(original, arguments, ctx)
            _audit(ctx, slug, original, error=None)
            return ToolResult(id=call.id, name=call.name,
                              content=fence_result(result, source=f"mcp:{slug}:{original}"))
        except Exception as exc:
            _audit(ctx, slug, original, error=type(exc).__name__)
            # Provider exceptions can contain bearer tokens or cell contents.
            return ToolResult(id=call.id, name=call.name, error=f"{type(exc).__name__}: Sheets operation failed")
    spec = build_spec(ctx, slug)
    if spec is None:
        return ToolResult(id=call.id, name=call.name, error=f"unknown_tool:{call.name}")

    try:
        if slug == PLAYWRIGHT:
            check_playwright_call(original, arguments, allowed_hosts=spec.allowed_hosts)
        if slug in (EXA, FIRECRAWL):
            check_research_call(slug, original, arguments, allowed_hosts=spec.allowed_hosts)
        result = get_client().call_tool(spec, original, arguments)
        content = fence_result(result, source=f"mcp:{slug}:{original}")
        _audit(ctx, slug, original, error=None)
        return ToolResult(id=call.id, name=call.name, content=content)
    except SsrfBlocked as exc:
        _audit(ctx, slug, original, error="ssrf_blocked")
        return ToolResult(id=call.id, name=call.name, error=f"ssrf_blocked:{exc}")
    except Exception as exc:  # noqa: BLE001 - tool failures must not crash generation
        logger.warning("mcp tool %s/%s failed: %s", slug, original, type(exc).__name__)
        _audit(ctx, slug, original, error=type(exc).__name__)
        return ToolResult(
            id=call.id,
            name=call.name,
            error=f"{type(exc).__name__}: {exc}",
        )


def ping_server(ctx, slug: str) -> dict[str, Any]:
    spec = build_spec(ctx, slug)
    if spec is None:
        raise AppError("MCP server is not enabled", status_code=400, code="mcp_disabled")
    tools = get_client().list_tools(spec)
    names = [t.name for t in tools]
    return {"server": slug, "tools": names, "status": STATUS_CONNECTED}


def _audit(ctx, slug: str, original: str, *, error: str | None) -> None:
    try:
        record_audit(
            ctx.db,
            ctx.principal,
            action="mcp_call",
            resource_type="mcp_integration",
            resource_id=slug,
            details={"server": slug, "tool": original, "error": error},
        )
    except Exception:  # noqa: BLE001 - audit must not break the tool loop
        logger.exception("failed to audit mcp_call")


# Re-export status constants for the HTTP layer.
__all__ = [
    "STATUS_CONNECTED",
    "all_static_definitions",
    "execute_mcp_tool",
    "exposed_name",
    "mcp_definitions_for",
    "parse_exposed_name",
    "ping_server",
    "server_enabled",
]
