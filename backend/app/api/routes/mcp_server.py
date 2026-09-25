"""API routes for exposing Personal Knowledge AI as a Custom MCP Server.

Provides:
- GET  /api/mcp/custom-server/status: Server status and tools manifest.
- GET  /api/mcp/custom-server/config: Claude Desktop & Cursor config snippets.
- POST /api/mcp/custom-server/tokens: Mint API keys for external MCP clients.
- POST /api/mcp/custom-server/rpc: Standard JSON-RPC 2.0 gateway for MCP clients.
- POST /api/mcp/custom-server/execute: Interactive tool tester for website UI.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

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
from app.security.deps import _uuid, get_or_create_default_org, resolve_principal
from app.security.jwt import JWTError, create_jwt, decode_jwt
from app.security.labels import Role, Sensitivity, normalize
from app.security.principal import Principal, owner_principal

router = APIRouter(prefix="/api/mcp/custom-server", tags=["custom-mcp-server"])

# In-memory queues for active SSE MCP sessions: sessionId -> asyncio.Queue
_SSE_SESSIONS: dict[str, asyncio.Queue] = {}


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


def _principal_from_raw_token(token: str, db: Session) -> Principal:
    """Decode token string and build a valid Principal."""
    payload = decode_jwt(token)
    default_org = get_or_create_default_org(db)
    org_id = _uuid(payload.get("org_id")) or default_org.id
    user_id = _uuid(payload.get("sub") or payload.get("user_id"))
    role = normalize(payload.get("role", Role.SOLUTIONS_ENGINEER), Role, Role.SOLUTIONS_ENGINEER)
    if role in (Role.OWNER, Role.ADMIN):
        return owner_principal(org_id, user_id)
    return Principal(
        org_id=org_id,
        user_id=user_id,
        role=role,
        max_sensitivity=Sensitivity.CUSTOMER_DATA,
        allow_vendor_restricted=True,
        account_refs=None,
        include_unapproved=True,
        label="mcp",
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
    script_url: str = ""
    sse_url: str = ""
    claude_desktop_config: dict[str, Any]
    remote_python_config: dict[str, Any] = Field(default_factory=dict)
    remote_npx_config: dict[str, Any] = Field(default_factory=dict)
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


@router.get("/script")
def download_mcp_script() -> Response:
    """Download the stdio MCP bridge script for clients that want a local copy."""
    workspace_root = Path(__file__).resolve().parent.parent.parent.parent.parent
    script_file = workspace_root / "scripts" / "mcp_server.py"
    if not script_file.exists():
        # Fallback to current working directory
        script_file = Path("scripts/mcp_server.py")
    if not script_file.exists():
        raise HTTPException(status_code=404, detail="Bridge script not found")
    content = script_file.read_text(encoding="utf-8")
    return Response(
        content=content,
        media_type="text/x-python",
        headers={
            "Content-Disposition": 'attachment; filename="mcp_server.py"',
            "Content-Type": "text/x-python; charset=utf-8",
        },
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

    script_url = f"{api_url}/api/mcp/custom-server/script"
    sse_url = f"{api_url}/api/mcp/custom-server/sse"

    sample_token = _mint_mcp_jwt(
        principal=principal,
        expires_minutes=60 * 24 * 30,
    )

    # Option 1 (Zero-Install Remote via Python): Executes in memory via URL, ZERO local files needed
    python_bootstrap = f"import urllib.request; exec(urllib.request.urlopen('{script_url}').read().decode('utf-8'))"
    remote_python_snippet = {
        "mcpServers": {
            SERVER_NAME: {
                "command": "python",
                "args": ["-c", python_bootstrap],
                "env": {
                    "PERSONAL_KNOWLEDGE_API_URL": api_url,
                    "PERSONAL_KNOWLEDGE_API_KEY": sample_token,
                },
            }
        }
    }

    # Option 2 (Zero-Install Remote via NPX): Uses standard mcp-remote package over SSE
    remote_npx_snippet = {
        "mcpServers": {
            SERVER_NAME: {
                "command": "npx",
                "args": [
                    "-y",
                    "mcp-remote@latest",
                    sse_url,
                    "--header",
                    f"Authorization: Bearer {sample_token}",
                ],
            }
        }
    }

    # Option 3 (Local File): If user explicitly downloads mcp_server.py
    local_script_snippet = {
        "mcpServers": {
            SERVER_NAME: {
                "command": "python",
                "args": [script_path if os.path.exists(script_path) else "mcp_server.py"],
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
                "args": ["-c", python_bootstrap],
                "env": {
                    "PERSONAL_KNOWLEDGE_API_URL": api_url,
                    "PERSONAL_KNOWLEDGE_API_KEY": sample_token,
                },
            }
        }
    }

    instructions = {
        "zero_download_python": (
            "Recommended: Paste the Python zero-download snippet into claude_desktop_config.json. "
            "It runs the bridge in memory directly from your server without requiring any downloaded files."
        ),
        "zero_download_npx": (
            "Alternative: Paste the npx snippet into claude_desktop_config.json. "
            "Requires Node.js and connects over remote SSE without any local files."
        ),
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
        script_url=script_url,
        sse_url=sse_url,
        claude_desktop_config=remote_python_snippet,
        remote_python_config=remote_python_snippet,
        remote_npx_config=remote_npx_snippet,
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


@router.get("/sse")
async def mcp_sse_endpoint(
    request: Request,
    token: str | None = Query(None),
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
):
    """Server-Sent Events (SSE) stream for MCP clients connecting remotely.
    
    Compatible with mcp-remote, Cursor, Claude Desktop, and Streamable HTTP.
    """
    raw_token = None
    if authorization and authorization.lower().startswith("bearer "):
        raw_token = authorization[7:].strip()
    elif token:
        raw_token = token.strip()

    if not raw_token:
        # In non-production, fallback to default principal if available
        if settings.auth_mode == "owner_dev" and settings.environment.lower() != "production":
            pass
        else:
            raise HTTPException(status_code=401, detail="Authentication token required (Bearer header or ?token=)")

    session_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    _SSE_SESSIONS[session_id] = queue

    base_url = str(request.base_url).rstrip("/")
    endpoint_uri = f"{base_url}/api/mcp/custom-server/message?sessionId={session_id}"

    async def event_generator():
        # Step 1: Send endpoint discovery event according to MCP SSE transport spec
        yield f"event: endpoint\ndata: {endpoint_uri}\n\n"
        try:
            while True:
                try:
                    # Wait for next outgoing message or send keepalive
                    msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                    if msg is None:
                        break
                    yield f"event: message\ndata: {json.dumps(msg)}\n\n"
                except asyncio.TimeoutError:
                    # Periodic keepalive ping to prevent proxy/cloud drops
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            _SSE_SESSIONS.pop(session_id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/message")
async def mcp_message_callback(
    request: Request,
    sessionId: str = Query(...),
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    """POST endpoint for MCP clients streaming JSON-RPC requests over an active SSE session."""
    raw_token = None
    if authorization and authorization.lower().startswith("bearer "):
        raw_token = authorization[7:].strip()

    try:
        if raw_token:
            principal = _principal_from_raw_token(raw_token, db)
        else:
            default_org = get_or_create_default_org(db)
            principal = owner_principal(default_org.id)
    except Exception as exc:
        return Response(
            content=json.dumps({"jsonrpc": "2.0", "error": {"code": -32600, "message": f"Auth error: {exc}"}}),
            media_type="application/json",
            status_code=401,
        )

    try:
        body = await request.json()
    except Exception:
        return Response(
            content=json.dumps({"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error: Invalid JSON"}}),
            media_type="application/json",
            status_code=400,
        )

    response = handle_mcp_jsonrpc_request(db, principal, body)

    # Deliver response over the active SSE session if connected
    queue = _SSE_SESSIONS.get(sessionId)
    if queue:
        await queue.put(response)
        return Response(status_code=202)

    # Fallback to direct HTTP reply if SSE session disconnected
    return Response(
        content=json.dumps(response),
        media_type="application/json",
        status_code=200,
    )


@router.post("/rpc")
async def jsonrpc_gateway(
    request: Request,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    """JSON-RPC 2.0 endpoint for MCP clients connecting over HTTP."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return {
            "jsonrpc": "2.0",
            "error": {"code": -32600, "message": "Missing Bearer Authorization header"},
        }

    token = authorization[7:].strip()
    try:
        principal = _principal_from_raw_token(token, db)
    except Exception as exc:
        return {
            "jsonrpc": "2.0",
            "error": {"code": -32600, "message": f"Invalid or expired authorization token: {exc}"},
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

