"""Launch specs for the three Phase 9 MCP servers.

Command lists only. Credentials and org config are applied at call time.

Package versions are pinned (audit finding 12): `npx -y pkg` or `pkg@latest` would run
whatever was published most recently, inside our process tree. Bump these on purpose,
after reading the changelog.
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

BRAVE_PACKAGE = "@brave/brave-search-mcp-server@2.1.3"
PLAYWRIGHT_PACKAGE = "@playwright/mcp@0.0.80"
MS365_PACKAGE = "@softeria/ms-365-mcp-server@0.156.2"


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
    return ("-y", BRAVE_PACKAGE)


def playwright_args() -> tuple[str, ...]:
    return ("-y", PLAYWRIGHT_PACKAGE, "--headless", "--isolated")


def ms365_args() -> tuple[str, ...]:
    return (
        "-y",
        MS365_PACKAGE,
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
