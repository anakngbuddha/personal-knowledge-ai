"""Unit tests for Custom MCP Server (read & write tools and JSON-RPC gateway)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from app.mcp.custom_server import (
    MCP_PROTOCOL_VERSION,
    MCP_TOOLS,
    SERVER_NAME,
    SERVER_VERSION,
    execute_mcp_tool_call,
    handle_mcp_jsonrpc_request,
)
from app.security.principal import Principal, Role


@pytest.fixture
def mock_principal():
    return Principal(
        user_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        role=Role.SOLUTIONS_ENGINEER,
    )


def test_mcp_tools_manifest_contains_read_and_write():
    read_tools = [t for t in MCP_TOOLS if t.get("category") == "read"]
    write_tools = [t for t in MCP_TOOLS if t.get("category") == "write"]

    assert len(read_tools) >= 7
    assert len(write_tools) >= 5

    names = {t["name"] for t in MCP_TOOLS}
    assert "search_knowledge" in names
    assert "ask_intelligence" in names
    assert "read_document" in names
    assert "list_documents" in names
    assert "create_note" in names
    assert "upload_text_document" in names
    assert "add_catalog_product" in names
    assert "link_catalog_products" in names


def test_mcp_jsonrpc_initialize(mock_principal):
    db = MagicMock()
    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {},
    }
    resp = handle_mcp_jsonrpc_request(db, mock_principal, req)
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == 1
    assert resp["result"]["serverInfo"]["name"] == SERVER_NAME
    assert resp["result"]["protocolVersion"] == MCP_PROTOCOL_VERSION
    assert "tools" in resp["result"]["capabilities"]


def test_mcp_jsonrpc_tools_list(mock_principal):
    db = MagicMock()
    req = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
    }
    resp = handle_mcp_jsonrpc_request(db, mock_principal, req)
    assert resp["id"] == 2
    tools = resp["result"]["tools"]
    assert len(tools) == len(MCP_TOOLS)
    assert any(t["name"] == "search_knowledge" for t in tools)
    assert any(t["name"] == "create_note" for t in tools)


def test_mcp_tool_execute_read_search_knowledge(mock_principal, monkeypatch):
    db = MagicMock()
    mock_hit = MagicMock(
        chunk_id="c1",
        document_id="d1",
        document_title="Title 1",
        citation="Doc 1",
        text="Sample passage text",
        rrf_score=0.95,
        page_number=1,
        vendor="Acme",
    )
    mock_search = MagicMock(hits=[mock_hit])
    monkeypatch.setattr("app.mcp.custom_server.run_search", lambda *args, **kwargs: mock_search)
    monkeypatch.setattr("app.mcp.custom_server._get_workspace_id", lambda *args: uuid.uuid4())

    result = execute_mcp_tool_call(db, mock_principal, "search_knowledge", {"query": "architecture", "top_k": 3})
    assert "error" not in result
    assert result["total_hits"] == 1
    assert result["results"][0]["text"] == "Sample passage text"


def test_mcp_tool_execute_write_create_note(mock_principal, monkeypatch):
    db = MagicMock()
    mock_note = MagicMock(id=uuid.uuid4(), title="Test Note")
    monkeypatch.setattr("app.mcp.custom_server.notes_service.create_note", lambda *args, **kwargs: mock_note)
    monkeypatch.setattr("app.mcp.custom_server._get_workspace_id", lambda *args: uuid.uuid4())

    result = execute_mcp_tool_call(
        db,
        mock_principal,
        "create_note",
        {"title": "Test Note", "body": "# Content"},
    )
    assert result["success"] is True
    assert result["title"] == "Test Note"


def test_mcp_tool_execute_write_add_catalog_product(mock_principal, monkeypatch):
    db = MagicMock()
    mock_prod = MagicMock()
    mock_prod.id = uuid.uuid4()
    mock_prod.name = "Postgres"
    mock_prod.vendor = "Acme"
    monkeypatch.setattr("app.mcp.custom_server.CatalogService.create_product", lambda *args, **kwargs: mock_prod)
    monkeypatch.setattr("app.mcp.custom_server._get_workspace_id", lambda *args: uuid.uuid4())

    result = execute_mcp_tool_call(
        db,
        mock_principal,
        "add_catalog_product",
        {"name": "Postgres", "vendor": "Acme"},
    )
    assert result["success"] is True
    assert result["name"] == "Postgres"


def test_mcp_jsonrpc_tools_call_wrapper(mock_principal, monkeypatch):
    db = MagicMock()
    mock_prod = MagicMock()
    mock_prod.id = uuid.uuid4()
    mock_prod.name = "Redis"
    mock_prod.vendor = "Redis Ltd"
    monkeypatch.setattr("app.mcp.custom_server.CatalogService.create_product", lambda *args, **kwargs: mock_prod)
    monkeypatch.setattr("app.mcp.custom_server._get_workspace_id", lambda *args: uuid.uuid4())

    req = {
        "jsonrpc": "2.0",
        "id": 10,
        "method": "tools/call",
        "params": {
            "name": "add_catalog_product",
            "arguments": {"name": "Redis", "vendor": "Redis Ltd"},
        },
    }
    resp = handle_mcp_jsonrpc_request(db, mock_principal, req)
    assert resp["id"] == 10
    assert resp["result"]["isError"] is False
    content_text = resp["result"]["content"][0]["text"]
    assert "Redis" in content_text
