"""Restricted sheet tools enforce tenant, workspace, scope, and immutable exports."""

import json
import uuid

import httpx
from httpx import Client as RealHttpClient
import pytest
from cryptography.fernet import Fernet

from app.core.config import settings
from app.db.models import AuditLog, McpIntegration
from app.mcp.credentials import encrypt_secret
from app.mcp.registry_bridge import mcp_definitions_for
from app.security.labels import Role
from app.security.principal import Principal
from app.tools.registry import ToolContext, execute_tool
from app.tools.schema import ToolCall
from tests.test_opportunities import sales_api  # noqa: F401
from tests.test_sales_quotes import _setup


@pytest.fixture
def configured(sales_api, monkeypatch):
    from app.mcp import sheets_tools
    client, current, (org_a, org_b) = sales_api
    opportunity = client.post("/api/opportunities", json={"title": "Sheet pilot"}).json()
    workspace = uuid.UUID(opportunity["workspace_id"])
    monkeypatch.setattr(settings, "mcp_enabled", True)
    monkeypatch.setattr(settings, "mcp_credentials_key", Fernet.generate_key().decode())
    db = current["session_factory"]()
    db.add(McpIntegration(org_id=org_a, server_slug="google_sheets", enabled=True,
                          secret_ciphertext=encrypt_secret("tenant-secret"), config={"sheet_targets": [{
                              "alias": "pilot", "workspace_id": str(workspace),
                              "spreadsheet_id": "sheet_pilot_123456", "tab": "Draft", "draft": True,
                          }]}))
    db.commit()
    calls = []

    def respond(request):
        calls.append(request)
        if request.method == "PUT":
            body = json.loads(request.content)
            return httpx.Response(200, json={"updatedCells": sum(len(row) for row in body["values"])})
        return httpx.Response(200, json={"values": [["Review this source", "1.25"]]})

    original_client = httpx.Client
    monkeypatch.setattr(sheets_tools.httpx, "Client", lambda **kwargs: original_client(
        transport=httpx.MockTransport(respond), **kwargs
    ))
    monkeypatch.setattr(sheets_tools, "service_account_access_token", lambda secret: "tenant-token")
    ctx = ToolContext(db, current["principal"], workspace)
    try:
        yield ctx, calls, org_b, client, current
    finally:
        db.close()


def run(ctx, tool="read_sheet", **arguments):
    return execute_tool(ToolCall("sheet-call", f"mcp_google_sheets_{tool}", arguments), ctx)


def test_read_and_write_draft_are_scoped_fenced_literal_and_audited(configured):
    ctx, calls, *_ = configured
    names = {tool.name for tool in mcp_definitions_for(ctx)}
    assert {"mcp_google_sheets_read_sheet", "mcp_google_sheets_write_draft"} <= names
    result = run(ctx, sheet_alias="pilot")
    assert result.error is None and result.content["untrusted"]
    result = run(ctx, "write_draft", sheet_alias="pilot", values=[["=IMPORTXML('evil')", "12.50"]])
    assert result.error is None
    assert calls[-1].url.params["valueInputOption"] == "RAW"
    assert calls[-1].headers["Authorization"] == "Bearer tenant-token"
    assert json.loads(calls[-1].content)["values"][0][0].startswith("=IMPORTXML")
    assert len(ctx.db.query(AuditLog).filter(AuditLog.action == "mcp_call").all()) == 2


def test_other_tenant_and_workspace_have_no_tools_or_access(configured):
    ctx, calls, org_b, *_ = configured
    for other in (ToolContext(ctx.db, Principal(org_id=org_b, user_id=uuid.uuid4(), role=Role.SALES), ctx.workspace_id),
                  ToolContext(ctx.db, ctx.principal, uuid.uuid4())):
        assert not any(tool.name.startswith("mcp_google_sheets_") for tool in mcp_definitions_for(other))
        assert run(other, sheet_alias="pilot").error
    assert not calls


@pytest.mark.parametrize("arguments", [
    {"sheet_alias": "pilot", "org_id": str(uuid.uuid4())},
    {"sheet_alias": "pilot", "access_token": "injected"},
    {"sheet_alias": "pilot", "range": "Other!A1"},
    {"sheet_alias": "https://evil.invalid"},
    {"sheet_alias": "unknown"},
])
def test_reject_model_destinations_and_credentials_before_network(configured, arguments):
    ctx, calls, *_ = configured
    assert run(ctx, **arguments).error
    assert not calls


def test_read_scope_cannot_write_and_payloads_are_bounded(configured):
    ctx, calls, *_ = configured
    ctx.principal = Principal(org_id=ctx.principal.org_id, user_id=ctx.principal.user_id,
                              role=Role.SALES, scopes=frozenset({"mcp:read"}))
    assert "mcp_google_sheets_write_draft" not in {tool.name for tool in mcp_definitions_for(ctx)}
    assert run(ctx, "write_draft", sheet_alias="pilot", values=[["x"]]).error
    for values in ([], [["x"]] * 101, [["x"] * 27], [["x" * 2001]], [["x" * 1000] * 26] * 2, [[5]]):
        assert run(ctx, "write_draft", sheet_alias="pilot", values=values).error
    assert not calls


def test_admin_cannot_configure_another_tenants_workspace(configured):
    ctx, _, _, client, current = configured
    current["principal"] = Principal(org_id=ctx.principal.org_id, user_id=uuid.uuid4(), role=Role.ADMIN)
    response = client.put("/integrations/mcp/google_sheets", json={"enabled": True, "sheet_targets": [{
        "alias": "bad", "workspace_id": str(uuid.uuid4()), "spreadsheet_id": "sheet_pilot_123456",
        "tab": "Draft", "draft": True,
    }]})
    assert response.status_code == 422


def test_external_mcp_surface_is_restricted_and_tenant_scoped(configured):
    from app.mcp.custom_server import handle_mcp_jsonrpc_request
    ctx, calls, org_b, *_ = configured
    manifest = handle_mcp_jsonrpc_request(ctx.db, ctx.principal, {"id": 1, "method": "tools/list"})
    assert "mcp_google_sheets_read_sheet" in {tool["name"] for tool in manifest["result"]["tools"]}
    result = handle_mcp_jsonrpc_request(ctx.db, ctx.principal, {
        "id": 2, "method": "tools/call", "params": {
            "name": "mcp_google_sheets_read_sheet", "arguments": {"sheet_alias": "pilot"},
        },
    })
    assert not result["result"]["isError"] and calls
    other = Principal(org_id=org_b, user_id=uuid.uuid4(), role=Role.SALES)
    manifest = handle_mcp_jsonrpc_request(ctx.db, other, {"id": 3, "method": "tools/list"})
    assert not any(tool["name"].startswith("mcp_google_sheets_") for tool in manifest["result"]["tools"])


def test_issued_quote_export_cannot_be_overwritten_even_when_configured_as_draft(configured):
    from app.db.models import SalesQuoteExport
    ctx, calls, _, client, current = configured
    sales_api_tuple = (client, current, (ctx.principal.org_id, uuid.uuid4()))
    _, _, _, opportunity_id, requirement_id, request = _setup(sales_api_tuple)
    client.patch(f"/api/opportunities/{opportunity_id}/requirements/{requirement_id}", json={
        "version": 1, "coverage_state": "covered", "coverage_note": "reviewed",
    })
    version = client.post(f"/api/sales/opportunities/{opportunity_id}/quotes", json=request).json()
    ctx.db.add(SalesQuoteExport(org_id=ctx.principal.org_id, quote_version_id=uuid.UUID(version["id"]),
                               status="completed", external_id="sheet_pilot_123456"))
    ctx.db.commit()
    result = run(ctx, "write_draft", sheet_alias="pilot", values=[["Overwrite approved quote"]])
    assert result.error and not calls


def test_sheet_response_limits_and_provider_errors_are_sanitized(configured, monkeypatch):
    from app.mcp import sheets_tools
    ctx, _, *_ = configured
    for status, body in ((200, b"x" * 65537), (401, b"tenant-token secret cells")):
        monkeypatch.setattr(sheets_tools.httpx, "Client", lambda **kwargs: RealHttpClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(status, content=body)), **kwargs
        ))
        result = run(ctx, sheet_alias="pilot")
        assert result.error and "tenant-token" not in result.error and "secret cells" not in result.error
