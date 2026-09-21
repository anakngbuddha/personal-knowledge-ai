"""Launch specs for the three Phase 9 MCP servers.

Command lists only. Credentials and org config are applied at call time.
"""

from __future__ import annotations

from dataclasses import dataclass, field

BRAVE = "brave"
PLAYWRIGHT = "playwright"
MS365 = "ms365"

SERVER_SLUGS = (BRAVE, PLAYWRIGHT, MS365)

STATUS_DISCONNECTED = "disconnected"
STATUS_CONNECTED = "connected"
STATUS_ERROR = "error"
STATUS_DISABLED = "disabled"


@dataclass(frozen=True)
class ServerSpec:
    """How to reach one MCP server for one tenant."""

    slug: str
    org_id: str
    command: str = "npx"
    args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    http_url: str | None = None
    allowed_hosts: tuple[str, ...] = ()


def brave_args() -> tuple[str, ...]:
    return ("-y", "@brave/brave-search-mcp-server")


def playwright_args() -> tuple[str, ...]:
    return ("-y", "@playwright/mcp@latest", "--headless")


def ms365_args() -> tuple[str, ...]:
    return (
        "-y",
        "@softeria/ms-365-mcp-server",
        "--org-mode",
        "--read-only",
        "--preset",
        "mail,calendar,files,excel,contacts",
    )


def default_args(slug: str) -> tuple[str, ...]:
    if slug == BRAVE:
        return brave_args()
    if slug == PLAYWRIGHT:
        return playwright_args()
    if slug == MS365:
        return ms365_args()
    raise ValueError(f"unknown MCP server slug: {slug}")
