"""Phase 9 MCP client tests. No npx, Chromium, or live APIs."""

from __future__ import annotations

import uuid

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.models import AuditLog, Base, McpIntegration, Organization, Workspace
from app.db.session import get_db
from app.llm.fake import FakeLLMProvider
from app.llm.prompts import SYSTEM_PROMPT
from app.main import app
from app.mcp.client import FakeMcpClient
from app.mcp.credentials import decrypt_secret, encrypt_secret
from app.mcp.supervisor import set_client_override
from app.security.jwt import mint_token
from app.security.labels import Role
from app.security.principal import owner_principal
from app.tools.loop import run_tool_loop
from app.tools.registry import ToolContext, default_definitions, execute_tool
from app.tools.schema import ToolCall

client = TestClient(app)


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    return "JSON"


def _session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Organization.__table__,
            Workspace.__table__,
            McpIntegration.__table__,
            AuditLog.__table__,
        ],
    )
    SessionClass = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return SessionClass()


@pytest.fixture
def mcp_env(monkeypatch):
    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setattr(settings, "mcp_enabled", True)
    monkeypatch.setattr(settings, "mcp_credentials_key", key)
    monkeypatch.setattr(settings, "brave_api_key", "test-brave-key")
    monkeypatch.setattr(settings, "mcp_playwright_enabled", True)
    monkeypatch.setattr(settings, "mcp_ms365_enabled", True)
    fake = FakeMcpClient()
    fake.responses[("brave", "brave_web_search")] = {
        "results": [{"title": "Vendor SSO", "url": "https://example.com/sso"}]
    }
    set_client_override(fake)
    try:
        yield fake
    finally:
        set_client_override(None)


@pytest.fixture
def mcp_api(mcp_env, monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Organization.__table__,
            Workspace.__table__,
            McpIntegration.__table__,
            AuditLog.__table__,
        ],
    )
    SessionClass = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = SessionClass()
    org_a = Organization(id=uuid.uuid4(), slug="org-a", name="A")
    org_b = Organization(id=uuid.uuid4(), slug="org-b", name="B")
    db.add_all([org_a, org_b])
    db.commit()

    def _get_db():
        inner = SessionClass()
        try:
            yield inner
        finally:
            inner.close()

    app.dependency_overrides[get_db] = _get_db
    db.org_a_id = org_a.id
    db.org_b_id = org_b.id
    db.SessionClass = SessionClass
    try:
        yield db
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()


def test_mcp_disabled_hides_definitions(monkeypatch):
    monkeypatch.setattr(settings, "mcp_enabled", False)
    db = _session()
    org = Organization(id=uuid.uuid4(), slug="acme", name="Acme")
    db.add(org)
    db.commit()
    ws = Workspace(id=uuid.uuid4(), org_id=org.id, name="Default")
    db.add(ws)
    db.commit()
    ctx = ToolContext(db=db, principal=owner_principal(org.id), workspace_id=ws.id)
    names = {item.name for item in default_definitions(ctx)}
    assert not any(name.startswith("mcp_") for name in names)
    assert "tool_hybrid_search" in names


def test_brave_search_is_fenced_and_runs_in_loop(mcp_env):
    db = _session()
    org = Organization(id=uuid.uuid4(), slug="acme", name="Acme")
    db.add(org)
    db.commit()
    ws = Workspace(id=uuid.uuid4(), org_id=org.id, name="Default")
    db.add(ws)
    db.commit()
    db.add(McpIntegration(org_id=org.id, server_slug="brave", enabled=True, config={}, status="connected"))
    db.commit()
    ctx = ToolContext(db=db, principal=owner_principal(org.id), workspace_id=ws.id)
    tools = default_definitions(ctx)
    assert any(item.name == "mcp_brave_web_search" for item in tools)

    def _execute(call: ToolCall):
        return execute_tool(call, ctx)

    answer = run_tool_loop(
        FakeLLMProvider(),
        "Please search the web via Brave for vendor SSO docs",
        [],
        system_prompt=SYSTEM_PROMPT,
        history=None,
        tools=tools,
        execute=_execute,
    )
    assert answer.tool_calls
    assert answer.tool_results
    result = answer.tool_results[0]
    assert result.error is None
    assert result.content.get("untrusted") is True
    assert "UNTRUSTED_DOCUMENT_CONTENT" in result.content["text"]
    assert mcp_env.calls
    assert mcp_env.calls[0][0] == "brave"
    assert mcp_env.calls[0][1] == "brave_web_search"


def test_allowlist_rejects_blocked_mcp_tools(mcp_env):
    db = _session()
    org = Organization(id=uuid.uuid4(), slug="acme", name="Acme")
    db.add(org)
    db.commit()
    ws = Workspace(id=uuid.uuid4(), org_id=org.id, name="Default")
    db.add(ws)
    db.commit()
    ctx = ToolContext(db=db, principal=owner_principal(org.id), workspace_id=ws.id)
    blocked = [
        ToolCall(id="1", name="brave_image_search", arguments={"query": "x"}),
        ToolCall(id="2", name="browser_file_upload", arguments={"path": "/etc/passwd"}),
        ToolCall(id="3", name="mcp_brave_image_search", arguments={"query": "x"}),
        ToolCall(id="4", name="mcp_playwright_browser_file_upload", arguments={}),
    ]
    for call in blocked:
        result = execute_tool(call, ctx)
        assert result.error and result.error.startswith("unknown_tool:"), call.name
    assert mcp_env.calls == []


def test_playwright_metadata_url_is_ssrf_blocked(mcp_env):
    db = _session()
    org = Organization(id=uuid.uuid4(), slug="acme", name="Acme")
    db.add(org)
    db.commit()
    ws = Workspace(id=uuid.uuid4(), org_id=org.id, name="Default")
    db.add(ws)
    db.commit()
    db.add(McpIntegration(org_id=org.id, server_slug="playwright", enabled=True, config={}, status="connected"))
    db.commit()
    ctx = ToolContext(db=db, principal=owner_principal(org.id), workspace_id=ws.id)
    result = execute_tool(
        ToolCall(
            id="nav",
            name="mcp_playwright_browser_navigate",
            arguments={"url": "http://169.254.169.254/latest/meta-data"},
        ),
        ctx,
    )
    assert result.error
    assert "ssrf" in result.error.lower()
    assert mcp_env.calls == []


def test_research_mcp_is_tenant_scoped_and_fenced(mcp_env):
    from app.mcp.registry_bridge import build_spec
    from app.mcp.sandbox import allowed_original

    db = _session()
    first = Organization(id=uuid.uuid4(), slug="research-a", name="Research A")
    second = Organization(id=uuid.uuid4(), slug="research-b", name="Research B")
    db.add_all([first, second])
    db.commit()
    ws = Workspace(id=uuid.uuid4(), org_id=first.id, name="Default")
    db.add(ws)
    db.add_all([
        McpIntegration(org_id=first.id, server_slug="exa", enabled=True,
                       config={}, secret_ciphertext=encrypt_secret("exa-test"), status="disconnected"),
        McpIntegration(org_id=first.id, server_slug="firecrawl", enabled=True,
                       config={"allowed_hosts": ["example.com"]},
                       secret_ciphertext=encrypt_secret("fc-test"), status="disconnected"),
    ])
    db.commit()
    ctx = ToolContext(db=db, principal=owner_principal(first.id), workspace_id=ws.id)
    other = ToolContext(db=db, principal=owner_principal(second.id), workspace_id=ws.id)
    exa = build_spec(ctx, "exa")
    assert exa.http_url == "https://mcp.exa.ai/mcp"
    assert exa.http_headers == {"Authorization": "Bearer exa-test"}
    assert build_spec(other, "exa") is None
    assert not allowed_original("exa", "agent_run")
    assert not allowed_original("firecrawl", "firecrawl_find_tools")
    names = {item.name for item in default_definitions(ctx)}
    assert "mcp_exa_web_search_exa" in names
    assert "mcp_firecrawl_firecrawl_scrape" in names
    assert "mcp_exa_web_search_exa" not in {item.name for item in default_definitions(other)}
    found = execute_tool(ToolCall(id="search", name="mcp_exa_web_search_exa",
                                  arguments={"query": "vendor backup service", "numResults": 3}), ctx)
    assert found.error is None
    assert found.content["untrusted"] is True
    assert mcp_env.calls[-1][0:2] == ("exa", "web_search_exa")
    blocked = execute_tool(ToolCall(id="crawl", name="mcp_firecrawl_firecrawl_crawl",
                                    arguments={"url": "http://169.254.169.254/", "limit": 2}), ctx)
    assert blocked.error and "ssrf" in blocked.error.lower()
    assert mcp_env.calls[-1][0] == "exa"


def test_secret_roundtrip_is_not_logged(mcp_env, mcp_api: Session):
    secret = "super-secret-brave-key-do-not-log"
    token = mint_token(org_id=mcp_api.org_a_id, role=Role.ADMIN)
    resp = client.put(
        "/integrations/mcp/brave",
        headers={"Authorization": f"Bearer {token}"},
        json={"enabled": True, "secret": secret, "allowed_hosts": []},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["has_secret"] is True
    assert secret not in resp.text
    inner = mcp_api.SessionClass()
    try:
        row = inner.scalars(select(McpIntegration).where(McpIntegration.server_slug == "brave")).first()
        assert row is not None
        assert row.secret_ciphertext
        assert decrypt_secret(row.secret_ciphertext) == secret
        assert secret.encode() not in row.secret_ciphertext
        audits = list(inner.scalars(select(AuditLog).where(AuditLog.action == "mcp_upsert")))
        assert audits
        blob = str(audits[0].details)
        assert secret not in blob
    finally:
        inner.close()


def test_encrypt_decrypt_unit(mcp_env):
    token = "graph-refresh-token"
    blob = encrypt_secret(token)
    assert blob != token.encode()
    assert decrypt_secret(blob) == token


def test_viewer_cannot_put_credentials(mcp_api: Session):
    token = mint_token(org_id=mcp_api.org_a_id, role=Role.VIEWER)
    resp = client.put(
        "/integrations/mcp/brave",
        headers={"Authorization": f"Bearer {token}"},
        json={"enabled": True, "secret": "nope", "allowed_hosts": []},
    )
    assert resp.status_code == 403


def test_cross_tenant_get_is_404(mcp_api: Session):
    admin_a = mint_token(org_id=mcp_api.org_a_id, role=Role.ADMIN)
    created = client.put(
        "/integrations/mcp/brave",
        headers={"Authorization": f"Bearer {admin_a}"},
        json={"enabled": True, "allowed_hosts": []},
    )
    assert created.status_code == 200, created.text
    integration_id = created.json()["id"]
    admin_b = mint_token(org_id=mcp_api.org_b_id, role=Role.ADMIN)
    resp = client.get(
        f"/integrations/mcp/{integration_id}",
        headers={"Authorization": f"Bearer {admin_b}"},
    )
    assert resp.status_code == 404
    listed = client.get("/integrations/mcp", headers={"Authorization": f"Bearer {admin_b}"})
    assert listed.status_code == 200
    brave = next(item for item in listed.json()["integrations"] if item["server_slug"] == "brave")
    assert brave["id"] is None or brave["id"] != integration_id
    assert brave["has_secret"] is False
