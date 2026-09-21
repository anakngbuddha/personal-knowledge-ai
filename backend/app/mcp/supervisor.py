"""Process-wide MCP client holder. Tests inject FakeMcpClient here."""

from __future__ import annotations

from app.core.config import settings
from app.core.logging import get_logger
from app.mcp.client import McpClient, SdkMcpClient

logger = get_logger(__name__)

_override: McpClient | None = None
_live: McpClient | None = None
_started = False


def set_client_override(client: McpClient | None) -> None:
    """Replace the live SDK client. Used by unit tests; never used in production."""
    global _override
    _override = client


def get_client() -> McpClient:
    if _override is not None:
        return _override
    global _live
    if _live is None:
        _live = SdkMcpClient()
    return _live


def start_supervisor() -> None:
    global _started, _live
    if _started:
        return
    _started = True
    if not settings.mcp_enabled:
        logger.info("mcp supervisor idle (MCP_ENABLED=false)")
        return
    _live = SdkMcpClient()
    logger.info("mcp supervisor started")


def stop_supervisor() -> None:
    global _started, _live
    _started = False
    _live = None
    logger.info("mcp supervisor stopped")


def get_supervisor() -> None:
    """Kept for the package export; start/stop are the real lifecycle hooks."""
    return None
