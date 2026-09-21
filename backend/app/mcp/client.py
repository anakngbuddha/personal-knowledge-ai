"""MCP client protocol, test fake, and optional official-SDK transport."""

from __future__ import annotations

import asyncio
import concurrent.futures
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.mcp.servers import ServerSpec

logger = get_logger(__name__)


@dataclass(frozen=True)
class McpToolInfo:
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)


class McpClient(Protocol):
    def list_tools(self, spec: ServerSpec) -> list[McpToolInfo]: ...

    def call_tool(self, spec: ServerSpec, name: str, arguments: dict[str, Any]) -> Any: ...


class FakeMcpClient:
    """In-process double. Tests inject this so no npx/Chromium/network is required."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.list_calls: list[str] = []
        self.responses: dict[tuple[str, str], Any] = {}
        self.tools: dict[str, list[McpToolInfo]] = {
            "brave": [
                McpToolInfo("brave_web_search", "Brave web search"),
                McpToolInfo("brave_news_search", "Brave news search"),
                McpToolInfo("brave_image_search", "Brave image search"),
            ],
            "playwright": [
                McpToolInfo("browser_navigate", "Navigate"),
                McpToolInfo("browser_snapshot", "Snapshot"),
                McpToolInfo("browser_file_upload", "Upload a file"),
            ],
            "ms365": [
                McpToolInfo("search_mail", "Search Outlook mail"),
                McpToolInfo("search_files", "Search OneDrive/SharePoint"),
                McpToolInfo("send_mail", "Send mail"),
            ],
        }

    def list_tools(self, spec: ServerSpec) -> list[McpToolInfo]:
        self.list_calls.append(spec.slug)
        return list(self.tools.get(spec.slug, []))

    def call_tool(self, spec: ServerSpec, name: str, arguments: dict[str, Any]) -> Any:
        self.calls.append((spec.slug, name, dict(arguments)))
        if (spec.slug, name) in self.responses:
            return self.responses[(spec.slug, name)]
        return {"ok": True, "server": spec.slug, "tool": name, "arguments": arguments}


def _run_coro(coro, *, timeout: float):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result(timeout=timeout)


def _serialize_result(result: Any) -> Any:
    if result is None:
        return {}
    if hasattr(result, "model_dump"):
        try:
            return result.model_dump()
        except Exception:  # noqa: BLE001
            pass
    content = getattr(result, "content", None)
    if content is not None:
        texts: list[str] = []
        for item in content or []:
            text = getattr(item, "text", None)
            if text:
                texts.append(str(text))
            elif isinstance(item, dict) and item.get("text"):
                texts.append(str(item["text"]))
        structured = getattr(result, "structured_content", None)
        payload: dict[str, Any] = {"text": "\n".join(texts)}
        if structured:
            payload["structured"] = structured
        return payload
    if isinstance(result, dict):
        return result
    return {"text": str(result)}


class SdkMcpClient:
    """Official MCP Python SDK client. Spawned per call; not used in unit tests."""

    def list_tools(self, spec: ServerSpec) -> list[McpToolInfo]:
        timeout = float(settings.mcp_call_timeout_seconds)
        raw = _run_coro(self._alist_tools(spec), timeout=timeout)
        tools: list[McpToolInfo] = []
        for item in raw:
            tools.append(
                McpToolInfo(
                    name=str(item.get("name", "")),
                    description=str(item.get("description", "")),
                    input_schema=item.get("inputSchema") or item.get("input_schema") or {},
                )
            )
        return tools

    def call_tool(self, spec: ServerSpec, name: str, arguments: dict[str, Any]) -> Any:
        timeout = float(settings.mcp_call_timeout_seconds)
        return _run_coro(self._acall_tool(spec, name, arguments), timeout=timeout)

    async def _alist_tools(self, spec: ServerSpec) -> list[dict[str, Any]]:
        async with _connect(spec) as session:
            listed = await session.list_tools()
            tools = getattr(listed, "tools", listed) or []
            out: list[dict[str, Any]] = []
            for tool in tools:
                if hasattr(tool, "model_dump"):
                    out.append(tool.model_dump())
                elif isinstance(tool, dict):
                    out.append(tool)
                else:
                    out.append(
                        {
                            "name": getattr(tool, "name", ""),
                            "description": getattr(tool, "description", ""),
                            "inputSchema": getattr(tool, "inputSchema", {}) or {},
                        }
                    )
            return out

    async def _acall_tool(self, spec: ServerSpec, name: str, arguments: dict[str, Any]) -> Any:
        async with _connect(spec) as session:
            result = await session.call_tool(name, arguments)
            return _serialize_result(result)


def _connect(spec: ServerSpec):
    if spec.http_url:
        return _http_transport(spec.http_url)
    return _stdio_transport(spec)


def _stdio_transport(spec: ServerSpec):
    try:
        from mcp import Client, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError as exc:
        raise AppError(
            "MCP Python SDK is not installed",
            status_code=500,
            code="mcp_sdk_missing",
        ) from exc

    env = dict(spec.env) if spec.env else None
    params = StdioServerParameters(command=spec.command, args=list(spec.args), env=env)
    return Client(stdio_client(params))


def _http_transport(url: str):
    try:
        from mcp import Client
    except ImportError as exc:
        raise AppError(
            "MCP Python SDK is not installed",
            status_code=500,
            code="mcp_sdk_missing",
        ) from exc
    return Client(url)
