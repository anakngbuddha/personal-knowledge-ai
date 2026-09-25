"""API routes for exposing Personal Knowledge AI as a Custom MCP Server.

Provides:
- GET  /api/mcp/custom-server/status: Server status and tools manifest.
- GET  /api/mcp/custom-server/config: Claude Desktop & Cursor config snippets.
- POST /api/mcp/custom-server/tokens: Mint API keys for external MCP clients.
- POST /api/mcp/custom-server/rpc: Standard JSON-RPC 2.0 gateway for MCP clients.
- POST /api/mcp/custom-server/execute: Interactive tool tester for website UI.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from datetime import timedelta
from app.core.config import settings
from app.db.session import get_db
from app.mcp.custom_server import (
    MCP_PROTOCOL_VERSION,
    MCP_TOOLS,
    SERVER_NAME,
    SERVER_VERSION,
    execute_mcp_tool_call,
    handle_mcp_jsonrpc_request,
)
from app.security.deps import resolve_principal
from app.security.jwt import create_jwt
from app.security.principal import Principal

router = APIRouter(prefix="/api/mcp/custom-server", tags=["custom-mcp-server"])


def _mint_mcp_jwt(principal: Principal, expires_minutes: int) -> str:
    """Generate a JWT for external MCP clients."""
    return create_jwt(
        claims={
            "sub": str(principal.user_id) if principal.user_id else str(uuid.uuid4()),
            "org_id": str(principal.org_id),
            "role": principal.role,
        },
        expires_delta=timedelta(minutes=expires_minutes),
    )


class McpStatusOut(BaseModel):
    status: str
    server_name: str
    version: str
    protocol_version: str
    tools_count: int
    read_tools_count: int
    write_tools_count: int
    tools: list[dict[str, Any]]


class McpConfigOut(BaseModel):
    server_name: str
    server_script_path: str
    api_url: str
    claude_desktop_config: dict[str, Any]
    cursor_config: dict[str, Any]
    instructions: dict[str, str]


class McpTokenIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: str = Field(default="solutions_engineer")
    expires_minutes: int = Field(default=60 * 24 * 30)  # 30 days default for external agent


class McpTokenOut(BaseModel):
    token: str
    token_type: str = "bearer"
    expires_minutes: int
    server_name: str


class McpExecuteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    arguments: dict[str, Any] = Field(default_factory=dict)


class McpExecuteOut(BaseModel):
    tool: str
    result: dict[str, Any]
    is_error: bool


@router.get("/status", response_model=McpStatusOut)
def get_custom_mcp_status(
    principal: Principal = Depends(resolve_principal),
) -> McpStatusOut:
    """Return status and manifest of the custom MCP server."""
    read_count = sum(1 for t in MCP_TOOLS if t.get("category") == "read")
    write_count = sum(1 for t in MCP_TOOLS if t.get("category") == "write")

    return McpStatusOut(
        status="active",
        server_name=SERVER_NAME,
        version=SERVER_VERSION,
        protocol_version=MCP_PROTOCOL_VERSION,
        tools_count=len(MCP_TOOLS),
        read_tools_count=read_count,
        write_tools_count=write_count,
        tools=MCP_TOOLS,
    )


@router.get("/config", response_model=McpConfigOut)
def get_custom_mcp_config(
    request: Request,
    principal: Principal = Depends(resolve_principal),
) -> McpConfigOut:
    """Return configuration snippets for Claude Desktop, Cursor, and other tools."""
    workspace_root = Path(__file__).resolve().parent.parent.parent.parent.parent
    script_path = str(workspace_root / "scripts" / "mcp_server.py").replace("\\", "/")

    # Detect base URL
    base_url = str(request.base_url).rstrip("/")
    if "localhost" in base_url or "127.0.0.1" in base_url:
        api_url = f"http://localhost:{settings.port}"
    else:
        api_url = base_url

    sample_token = _mint_mcp_jwt(
        principal=principal,
        expires_minutes=60 * 24 * 30,
    )

    claude_snippet = {
        "mcpServers": {
            SERVER_NAME: {
                "command": "python",
                "args": [script_path],
                "env": {
                    "PERSONAL_KNOWLEDGE_API_URL": api_url,
                    "PERSONAL_KNOWLEDGE_API_KEY": sample_token,
                },
            }
        }
    }

    cursor_snippet = {
        "mcpServers": {
            SERVER_NAME: {
                "command": "python",
                "args": [script_path],
                "env": {
                    "PERSONAL_KNOWLEDGE_API_URL": api_url,
                    "PERSONAL_KNOWLEDGE_API_KEY": sample_token,
                },
            }
        }
    }

    instructions = {
        "claude_desktop_windows": (
            "Paste the configuration snippet into %APPDATA%\\Claude\\claude_desktop_config.json, "
            "then completely restart Claude Desktop."
        ),
        "claude_desktop_mac": (
            "Paste the configuration snippet into ~/Library/Application Support/Claude/claude_desktop_config.json, "
            "then restart Claude Desktop."
        ),
        "cursor": (
            "Paste into .cursor/mcp.json in your workspace or configure in Cursor Settings > Features > MCP."
        ),
    }

    return McpConfigOut(
        server_name=SERVER_NAME,
        server_script_path=script_path,
        api_url=api_url,
        claude_desktop_config=claude_snippet,
        cursor_config=cursor_snippet,
        instructions=instructions,
    )


@router.post("/tokens", response_model=McpTokenOut)
def generate_mcp_token(
    payload: McpTokenIn,
    principal: Principal = Depends(resolve_principal),
) -> McpTokenOut:
    """Generate a persistent access token for an external MCP client."""
    token = _mint_mcp_jwt(
        principal=principal,
        expires_minutes=payload.expires_minutes,
    )
    return McpTokenOut(
        token=token,
        token_type="bearer",
        expires_minutes=payload.expires_minutes,
        server_name=SERVER_NAME,
    )


@router.post("/execute", response_model=McpExecuteOut)
def execute_tool_endpoint(
    payload: McpExecuteIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> McpExecuteOut:
    """Execute any MCP tool interactively from the web UI."""
    result = execute_mcp_tool_call(db, principal, payload.name, payload.arguments)
    is_error = "error" in result
    return McpExecuteOut(
        tool=payload.name,
        result=result,
        is_error=is_error,
    )


@router.post("/rpc")
async def jsonrpc_gateway(
    request: Request,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    """JSON-RPC 2.0 endpoint for MCP clients connecting over HTTP."""
    from app.security.auth import decode_access_token

    if not authorization or not authorization.lower().startswith("bearer "):
        return {
            "jsonrpc": "2.0",
            "error": {"code": -32600, "message": "Missing Bearer Authorization header"},
        }

    token = authorization[7:].strip()
    try:
        principal = decode_access_token(token)
    except Exception:
        return {
            "jsonrpc": "2.0",
            "error": {"code": -32600, "message": "Invalid or expired authorization token"},
        }

    try:
        body = await request.json()
    except Exception:
        return {
            "jsonrpc": "2.0",
            "error": {"code": -32700, "message": "Parse error: Invalid JSON"},
        }

    if not isinstance(body, dict):
        return {
            "jsonrpc": "2.0",
            "error": {"code": -32600, "message": "Invalid Request object"},
        }

    return handle_mcp_jsonrpc_request(db, principal, body)
