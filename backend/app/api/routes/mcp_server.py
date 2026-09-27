"""API routes for exposing Personal Knowledge AI as a Custom MCP Server.

Provides:
- GET  /api/mcp/custom-server/status: Server status and tools manifest.
- GET  /api/mcp/custom-server/config: Claude Desktop & Cursor config snippets.
- POST /api/mcp/custom-server/tokens: Mint short-lived API keys for external MCP clients.
- GET  /api/mcp/custom-server/sse + POST /message: MCP SSE transport.
- POST /api/mcp/custom-server/rpc: Standard JSON-RPC 2.0 gateway for MCP clients.
- POST /api/mcp/custom-server/execute: Interactive tool tester for website UI.

Security model (audit findings 1 and 3):

* Every SSE open, every /message POST and every /rpc call carries a bearer token.
  The only exception is local owner_dev mode, and even then a /message without a
  token is accepted only for a session that was itself opened anonymously.
* A token becomes a Principal through `principal_from_claims`, the same membership +
  grant lookup the web API uses, on every message. Revoking a membership takes
  effect on the next call, not at token expiry.
* A /message must name a live session, and the caller must be the session's owner.
  There is no direct-HTTP fallback for unknown or disconnected sessions.
* MCP tokens are short-lived and scoped (`mcp:read`, plus `mcp:write` for SE+).
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db, scope_session_to_org
from app.mcp.custom_server import (
    MCP_PROTOCOL_VERSION,
    MCP_TOOLS,
    SERVER_NAME,
    SERVER_VERSION,
    execute_mcp_tool_call,
    handle_mcp_jsonrpc_request,
)
from app.security.deps import (
    dev_fallback_allowed,
    get_or_create_default_org,
    principal_from_claims,
    resolve_principal,
)
from app.security.jwt import JWTError, create_jwt, decode_jwt
from app.security.principal import MCP_READ_SCOPE, MCP_WRITE_SCOPE, Principal, owner_principal

router = APIRouter(prefix="/api/mcp/custom-server", tags=["custom-mcp-server"])


@dataclass
class McpSession:
    queue: asyncio.Queue
    org_id: str
    user_id: str | None
    anonymous_dev: bool
    created_at: float

    def owned_by(self, principal: Principal) -> bool:
        user = str(principal.user_id) if principal.user_id else None
        return self.org_id == str(principal.org_id) and self.user_id == user


# In-memory registry of active SSE MCP sessions: sessionId -> McpSession
_SSE_SESSIONS: dict[str, McpSession] = {}


def register_mcp_session(principal: Principal, *, anonymous_dev: bool = False) -> str:
    """Create a session bound to `principal`. Returns an unguessable session id."""
    limit = max(1, int(getattr(settings, "mcp_max_sse_sessions", 500)))
    if len(_SSE_SESSIONS) >= limit:
        raise HTTPException(status_code=503, detail="too many open MCP sessions; retry later")
    session_id = secrets.token_urlsafe(24)
    _SSE_SESSIONS[session_id] = McpSession(
        queue=asyncio.Queue(),
        org_id=str(principal.org_id),
        user_id=str(principal.user_id) if principal.user_id else None,
        anonymous_dev=anonymous_dev,
        created_at=time.time(),
    )
    return session_id


def _clamp_minutes(requested: int | None) -> int:
    default = int(getattr(settings, "mcp_token_default_minutes", 480))
    maximum = int(getattr(settings, "mcp_token_max_minutes", 1440))
    value = default if requested is None else int(requested)
    return max(5, min(value, maximum))


def mcp_scopes_for(principal: Principal) -> list[str]:
    scopes = [MCP_READ_SCOPE]
    if principal.can_write_catalog and principal.has_scope(MCP_WRITE_SCOPE):
        scopes.append(MCP_WRITE_SCOPE)
    return scopes


def _mint_mcp_jwt(principal: Principal, expires_minutes: int | None = None) -> str:
    """Generate a short-lived, scoped JWT for external MCP clients.

    The role claim is informational only: every call re-reads the membership.
    """
    claims: dict[str, Any] = {
        "org_id": str(principal.org_id),
        "role": principal.role,
        "typ": "mcp",
        "scope": " ".join(mcp_scopes_for(principal)),
        "jti": uuid.uuid4().hex,
    }
    if principal.user_id:
        claims["sub"] = str(principal.user_id)
    return create_jwt(claims=claims, expires_delta=timedelta(minutes=_clamp_minutes(expires_minutes)))


def _bearer(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        return token or None
    return None


def resolve_mcp_principal(db: Session, raw_token: str | None) -> Principal:
    """Token -> Principal via the shared membership/grant lookup. Raises HTTPException."""
    if not raw_token:
        if dev_fallback_allowed():
            principal = owner_principal(get_or_create_default_org(db).id)
            scope_session_to_org(db, principal.org_id)
            return principal
        raise HTTPException(status_code=401, detail="Authentication token required (Bearer header)")
    try:
        payload = decode_jwt(raw_token)
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="invalid or expired token") from exc
    principal = principal_from_claims(db, payload, label="mcp")
    scope_session_to_org(db, principal.org_id)
    return principal


def _principal_from_raw_token(token: str, db: Session) -> Principal:
    """Backwards-compatible name for resolve_mcp_principal."""
    return resolve_mcp_principal(db, token)


def _rpc_error(status_code: int, code: int, message: str, req_id: Any = None) -> Response:
    return Response(
        content=json.dumps({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}),
        media_type="application/json",
        status_code=status_code,
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
    token_expires_minutes: int = 0
    claude_desktop_config: dict[str, Any]
    remote_python_config: dict[str, Any] = Field(default_factory=dict)
    remote_npx_config: dict[str, Any] = Field(default_factory=dict)
    cursor_config: dict[str, Any]
    instructions: dict[str, str]


class McpTokenIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Deprecated and ignored: the role always comes from your membership.
    role: str | None = Field(default=None)
    # Clamped to MCP_TOKEN_MAX_MINUTES. Defaults to MCP_TOKEN_DEFAULT_MINUTES.
    expires_minutes: int | None = Field(default=None, ge=1)


class McpTokenOut(BaseModel):
    token: str
    token_type: str = "bearer"
    expires_minutes: int
    server_name: str
    scopes: list[str] = Field(default_factory=list)


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

    expires = _clamp_minutes(None)
    sample_token = _mint_mcp_jwt(principal=principal, expires_minutes=expires)

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
    del local_script_snippet  # kept for parity with the docs; the UI shows the remote options

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
        "token_lifetime": (
            f"The embedded token expires in {expires} minutes and is re-checked against your "
            "membership on every call. Mint a fresh one from this page when it expires."
        ),
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
        token_expires_minutes=expires,
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
    """Generate a short-lived, scoped access token for an external MCP client."""
    minutes = _clamp_minutes(payload.expires_minutes)
    token = _mint_mcp_jwt(principal=principal, expires_minutes=minutes)
    return McpTokenOut(
        token=token,
        token_type="bearer",
        expires_minutes=minutes,
        server_name=SERVER_NAME,
        scopes=mcp_scopes_for(principal),
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

    The session is bound to the principal that opened it.
    """
    raw_token = _bearer(authorization) or (token.strip() if token else None)
    principal = await run_in_threadpool(resolve_mcp_principal, db, raw_token)
    session_id = register_mcp_session(principal, anonymous_dev=raw_token is None)
    session = _SSE_SESSIONS[session_id]

    base_url = str(request.base_url).rstrip("/")
    endpoint_uri = f"{base_url}/api/mcp/custom-server/message?sessionId={session_id}"

    async def event_generator():
        # Step 1: Send endpoint discovery event according to MCP SSE transport spec
        yield f"event: endpoint\ndata: {endpoint_uri}\n\n"
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(session.queue.get(), timeout=15.0)
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
    raw_token = _bearer(authorization)
    session = _SSE_SESSIONS.get(sessionId)

    # A token is mandatory, except for a session that was opened anonymously in local
    # owner_dev mode (and dev mode still applies now).
    if raw_token is None and not (session is not None and session.anonymous_dev and dev_fallback_allowed()):
        return _rpc_error(401, -32600, "Authentication token required (Bearer header)")

    try:
        principal = await run_in_threadpool(resolve_mcp_principal, db, raw_token)
    except HTTPException as exc:
        return _rpc_error(exc.status_code, -32600, f"Auth error: {exc.detail}")

    if session is None:
        return _rpc_error(404, -32001, "Unknown or expired MCP session; reconnect to /sse")
    if not session.owned_by(principal):
        return _rpc_error(403, -32600, "This token does not own the MCP session")

    try:
        body = await request.json()
    except Exception:
        return _rpc_error(400, -32700, "Parse error: Invalid JSON")
    if not isinstance(body, dict):
        return _rpc_error(400, -32600, "Invalid Request object")

    response = await run_in_threadpool(handle_mcp_jsonrpc_request, db, principal, body)
    await session.queue.put(response)
    return Response(status_code=202)


@router.post("/rpc")
async def jsonrpc_gateway(
    request: Request,
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    """JSON-RPC 2.0 endpoint for MCP clients connecting over HTTP."""
    token = _bearer(authorization)
    if token is None:
        return _rpc_error(401, -32600, "Missing Bearer Authorization header")

    try:
        principal = await run_in_threadpool(resolve_mcp_principal, db, token)
    except HTTPException as exc:
        return _rpc_error(exc.status_code, -32600, f"Invalid or expired authorization token: {exc.detail}")

    try:
        body = await request.json()
    except Exception:
        return _rpc_error(400, -32700, "Parse error: Invalid JSON")

    if not isinstance(body, dict):
        return _rpc_error(400, -32600, "Invalid Request object")

    return await run_in_threadpool(handle_mcp_jsonrpc_request, db, principal, body)
