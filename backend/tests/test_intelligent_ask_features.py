"""Tests for Intelligent Ask mentions (@) and function handlers (/).

Covers:
- Mention parsing and resolution (@note, @product, @connector, @web)
- Slash command evaluation (/goal, /connections, /plan, /graphify-sync, /help, /briefing, /faq, /compare)
- Goal steering in prompt generation
- Schema serialization and validation for MentionTargetOut, ProductConnectionsOut
"""

import uuid
import pytest

from app.generation.handlers import (
    KNOWN_CONNECTORS,
    handle_slash_command,
    resolve_mentions,
    get_mention_targets,
)
from app.generation.schemas import (
    AskIn,
    AskOut,
    ConnectionNodeOut,
    MentionTargetOut,
    ProductConnectionsOut,
)
from app.llm.prompts import system_prompt_for
from app.security.principal import Principal, Role


def _make_principal() -> Principal:
    return Principal(user_id=uuid.uuid4(), org_id=uuid.uuid4(), role=Role.VIEWER)


def test_known_connectors():
    assert len(KNOWN_CONNECTORS) >= 5
    ids = [c["id"] for c in KNOWN_CONNECTORS]
    assert "brave" in ids
    assert "playwright" in ids
    assert "ms365" in ids
    assert "google_sheets" in ids
    for c in KNOWN_CONNECTORS:
        assert c["ref"].startswith("connector:")
        assert "name" in c
        assert "desc" in c


def test_slash_command_help():
    principal = _make_principal()
    res = handle_slash_command(None, None, principal, "/help")
    assert res is not None
    assert res.handled is True
    assert "Intelligent Ask Cheatsheet" in res.text
    assert "@note:" in res.text
    assert "/goal" in res.text
    assert "/connections" in res.text


def test_slash_command_goal():
    principal = _make_principal()
    # Set goal
    res = handle_slash_command(None, None, principal, "/goal Migrate legacy storage to S3")
    assert res is not None
    assert res.handled is True
    assert res.active_goal == "Migrate legacy storage to S3"
    assert "Active Session Goal set to" in res.text

    # Query goal without arg
    res2 = handle_slash_command(None, None, principal, "/goal", goal="Existing Goal")
    assert res2 is not None
    assert res2.handled is True
    assert "Existing Goal" in res2.text


def test_slash_command_plan():
    principal = _make_principal()
    res = handle_slash_command(None, None, principal, "/plan Deploy Kubernetes cluster on AWS")
    assert res is not None
    assert res.handled is False
    assert res.rewritten_question is not None
    assert "Deploy Kubernetes cluster on AWS" in res.rewritten_question
    assert "step-by-step implementation and execution plan" in res.rewritten_question


def test_slash_command_briefing_faq_compare():
    principal = _make_principal()

    # Briefing
    res_b = handle_slash_command(None, None, principal, "/briefing Atlas Core vs Cloud")
    assert res_b is not None
    assert res_b.handled is False
    assert "executive briefing" in res_b.rewritten_question

    # FAQ
    res_f = handle_slash_command(None, None, principal, "/faq API rate limits")
    assert res_f is not None
    assert res_f.handled is False
    assert "comprehensive FAQ" in res_f.rewritten_question

    # Compare
    res_c = handle_slash_command(None, None, principal, "/compare ProductA and ProductB")
    assert res_c is not None
    assert res_c.handled is False
    assert "comparative analysis" in res_c.rewritten_question


def test_slash_command_connections_without_arg():
    principal = _make_principal()
    ws_id = uuid.uuid4()
    res = handle_slash_command(None, ws_id, principal, "/connections")
    assert res is not None
    assert res.handled is True
    assert "Please specify a product name" in res.text


def test_system_prompt_with_goal():
    prompt_without_goal = system_prompt_for(enable_tools=False, strict_mode=True)
    assert "Active Session Goal" not in prompt_without_goal

    goal_text = "Ensure OWASP compliance across all endpoints"
    prompt_with_goal = system_prompt_for(enable_tools=False, strict_mode=True, goal=goal_text)
    assert "Active Session Goal" in prompt_with_goal
    assert goal_text in prompt_with_goal


def test_schemas_mention_and_connections():
    m = MentionTargetOut(
        id="note-1",
        ref="note:architecture",
        name="Architecture Overview",
        category="note",
        subtitle="Workspace Note",
        icon="note",
    )
    assert m.category == "note"
    assert m.ref == "note:architecture"

    conn = ProductConnectionsOut(
        product_id="prod-1",
        product_name="Atlas-Core",
        vendor="DeepAtlas",
        category="Platform",
        prerequisites=[
            ConnectionNodeOut(id="p-2", name="Postgres", relation_type="requires", evidence="DB dependency")
        ],
        conflicts=[
            ConnectionNodeOut(id="p-3", name="Legacy-V1", relation_type="conflicts_with", evidence="Protocol mismatch")
        ],
        integrations=[
            ConnectionNodeOut(id="p-4", name="Redis", relation_type="integrates_with", evidence="Cache layer")
        ],
        alternatives=[],
        collateral_count=2,
    )
    assert len(conn.prerequisites) == 1
    assert conn.prerequisites[0].relation_type == "requires"
    assert conn.conflicts[0].relation_type == "conflicts_with"

    ask_in = AskIn(question="How does @product:Atlas-Core work?", goal="Assess scalability")
    assert ask_in.goal == "Assess scalability"


def test_resolve_mentions_syntax():
    # Test parsing when workspace is None or empty db
    resolved = resolve_mentions(
        None,
        None,
        "org-1",
        "Tell me about @connector:brave and @web:https://docs.python.org and @note:Architecture and @product:Atlas-Core",
    )
    assert "brave" in resolved.prioritized_connectors
    assert "https://docs.python.org" in resolved.target_web_urls


# Exercise real SQL and persisted messages without requiring a PostgreSQL service.
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.routes import ask as ask_routes
from app.db import models
from app.generation import service
from app.generation.conversations import get_active_goal
from app.generation.handlers import get_product_connections_data
from app.llm.base import GroundedAnswer, GroundedAnswerChunk
from app.security.principal import owner_principal, restricted_principal


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(element, compiler, **kwargs):
    return "JSON"


@pytest.fixture
def ask_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    tables = [models.Organization, models.Workspace, models.Note, models.Document,
              models.VendorSource, models.Product, models.ProductEdge, models.Capability,
              models.ProductCapability, models.ReferenceArchitecture,
              models.ReferenceArchitectureProduct, models.Conversation, models.Message]
    models.Base.metadata.create_all(engine, tables=[model.__table__ for model in tables])
    with Session(engine, expire_on_commit=False) as db:
        org = models.Organization(id=uuid.uuid4(), slug="ask-test", name="Ask")
        db.add(org)
        workspace = models.Workspace(id=uuid.uuid4(), org_id=org.id, name="Desk")
        other = models.Workspace(id=uuid.uuid4(), org_id=org.id, name="Other")
        db.add_all([workspace, other])
        db.commit()
        db.test_workspace = workspace.id
        db.test_other = other.id
        db.test_org = org.id
        yield db
    engine.dispose()


def _product(db, name="Atlas Core", slug="atlas-core", workspace=None):
    product = models.Product(id=uuid.uuid4(), workspace_id=workspace or db.test_workspace,
        org_id=db.test_org, name=name, slug=slug, vendor="Atlas", category="Platform",
        description="Supports SAML federation", collateral_document_ids=[])
    db.add(product)
    db.commit()
    return product


@pytest.fixture
def ask_client(ask_db, monkeypatch):
    app = FastAPI()
    app.include_router(ask_routes.router)
    app.dependency_overrides[ask_routes.get_db] = lambda: ask_db
    app.dependency_overrides[ask_routes.resolve_principal] = lambda: restricted_principal(ask_db.test_org)
    monkeypatch.setattr(ask_routes, "_workspace_id_from_principal", lambda *_: ask_db.test_workspace)
    with TestClient(app) as client:
        yield client


def test_mention_search_scopes_all_categories_and_limits_queries(ask_db, ask_client):
    db = ask_db
    for workspace in (db.test_workspace, db.test_other):
        db.add(models.Note(org_id=db.test_org, workspace_id=workspace, title="Architecture", slug="architecture", body="SAML"))
        db.add(models.VendorSource(org_id=db.test_org, workspace_id=workspace,
            label="Docs" if workspace == db.test_workspace else "Other private website", url="https://docs.example/Guide"))
    product = _product(db)
    _product(db, name="Other private product", workspace=db.test_other)
    db.add(models.Document(org_id=db.test_org, workspace_id=db.test_workspace,
        filename="private.html", original_filename="Private", source_type="url", source_url="https://secret.example",
        file_type="html", storage_key="private", sensitivity="customer_data"))
    db.commit()
    statements = []
    listener = lambda *args: statements.append(args[2])
    event.listen(db.bind, "before_cursor_execute", listener)
    try:
        response = ask_client.get("/ask/mention-targets", params={"limit": 20})
    finally:
        event.remove(db.bind, "before_cursor_execute", listener)
    assert response.status_code == 200, response.text
    rows = response.json()
    assert {row["category"] for row in rows} == {"note", "product", "connector", "website"}
    assert not any("private" in row["name"].lower() or "secret.example" in row["ref"] for row in rows)
    assert sum("SELECT" in sql.upper() for sql in statements) == 1
    assert ask_client.get("/ask/mention-targets", params={"category": "product", "q": "Platform"}).json()[0]["name"] == product.name
    assert len(ask_client.get("/ask/mention-targets", params={"limit": 2}).json()) == 2
    assert ask_client.get("/ask/mention-targets", params={"category": "invalid"}).status_code == 422
    assert ask_client.get("/ask/mention-targets", params={"limit": 0}).status_code == 422
    assert ask_client.get("/ask/mention-targets", params={"category": "note", "q": "%"}).json() == []


def test_direct_website_autocomplete_keeps_case(ask_client):
    rows = ask_client.get("/ask/mention-targets", params={"category": "website", "q": "https://docs.example/API/Guide"}).json()
    assert rows[0]["ref"] == "web:https://docs.example/API/Guide"


def test_connections_returns_conflicts_and_prefers_exact_product(ask_db, ask_client):
    db = ask_db
    _product(db, name="Atlas Core Extended", slug="atlas-extended")
    root = _product(db)
    others = [_product(db, name=name, slug=name.lower()) for name in ("Database", "Legacy", "Cache", "Cloud")]
    for target, relation in zip(others, ("requires", "conflicts_with", "integrates_with", "alternative_to")):
        db.add(models.ProductEdge(org_id=db.test_org, workspace_id=db.test_workspace,
            source_product_id=root.id, target_product_id=target.id, relation_type=relation,
            status=models.EdgeStatus.APPROVED, evidence="Vendor guide"))
    db.commit()
    for query in (str(root.id), root.slug, root.name):
        response = ask_client.get("/ask/product-connections", params={"product": query})
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["product_id"] == str(root.id)
        assert [result[k][0]["name"] for k in ("prerequisites", "conflicts", "integrations", "alternatives")] == [p.name for p in others]
    assert ask_client.get("/ask/product-connections", params={"product": "missing"}).status_code == 404
    isolated = _product(db, name="Isolated", slug="isolated", workspace=db.test_other)
    assert get_product_connections_data(db, db.test_workspace, str(isolated.id)) is None


def test_graph_failures_are_not_reported_as_no_dependencies(ask_db, monkeypatch):
    root = _product(ask_db)
    monkeypatch.setattr("app.generation.handlers.CatalogService.query_impact", Mock(side_effect=RuntimeError("failed")))
    with pytest.raises(RuntimeError, match="failed"):
        get_product_connections_data(ask_db, ask_db.test_workspace, root.slug)


@pytest.fixture
def generation_harness(ask_db, monkeypatch):
    monkeypatch.setattr(service, "check_rate_limit", lambda *_: None)
    monkeypatch.setattr(service, "check_token_budget", lambda *_: None)
    monkeypatch.setattr(service, "record_token_usage", lambda *_: None)
    monkeypatch.setattr(service, "_prepare_context", lambda *_a, **_k: service.PreparedContext(
        chunks=[], sources=[], relationships_block="", needs_web=False, search_query="test"))
    provider = Mock()
    provider.model_id = "test"
    provider.generate_grounded_answer.side_effect = lambda *_a, **_k: GroundedAnswer(
        text="Generated answer", citations=[], model_id="test", prompt_version="test")
    provider.stream_grounded_answer.side_effect = lambda *_a, **_k: iter([
        GroundedAnswerChunk(delta="Streaming answer"), GroundedAnswerChunk(delta="", done=True)])
    monkeypatch.setattr(service, "get_llm_provider", lambda: provider)
    return dict(db=ask_db, principal=owner_principal(ask_db.test_org), workspace_id=ask_db.test_workspace,
        enable_tools=False, web_search=False), provider


@pytest.mark.parametrize("stream", [False, True])
def test_goal_persists_steers_and_clears_in_both_paths(generation_harness, stream, ask_client):
    kwargs, provider = generation_harness
    def run(question, **extras):
        if stream:
            return list(service.ask_stream(**kwargs, question=question, **extras))[-1]
        return service.ask(**kwargs, question=question, **extras)
    first = run("/goal Prepare cloud deployment")
    assert first.active_goal == "Prepare cloud deployment"
    assert not provider.generate_grounded_answer.called
    conv_id = first.conversation_id
    assert get_active_goal(kwargs["db"], conversation_id=uuid.UUID(conv_id)) == first.active_goal
    second = run("What is next?", conversation_id=conv_id)
    assert second.active_goal == first.active_goal
    generate = provider.stream_grounded_answer if stream else provider.generate_grounded_answer
    assert first.active_goal in generate.call_args.kwargs["system_prompt"]
    assert ask_client.get(f"/conversations/{conv_id}").json()["goal"] == first.active_goal
    assert run("/goal done", conversation_id=conv_id).active_goal is None
    run("What remains?", conversation_id=conv_id)
    assert "Active Session Goal" not in generate.call_args.kwargs["system_prompt"]
    assert ask_client.get(f"/conversations/{conv_id}").json()["goal"] is None


def test_plan_generates_and_preserves_original_command(generation_harness):
    kwargs, provider = generation_harness
    result = service.ask(**kwargs, question="/plan Deploy SSO")
    assert result.text == "Generated answer"
    assert "step-by-step" in provider.generate_grounded_answer.call_args.args[0]
    user = kwargs["db"].scalar(select(models.Message).where(models.Message.role == "user"))
    assert user.content == "/plan Deploy SSO"


def test_connections_card_restored_from_history(generation_harness, ask_client):
    kwargs, _ = generation_harness
    root = _product(kwargs["db"])
    answer = list(service.ask_stream(**kwargs, question=f"/connections {root.slug}"))[-1]
    assert answer.connections_result.product_name == root.name
    output = ask_client.get(f"/conversations/{answer.conversation_id}").json()
    assert output["messages"][-1]["connections_result"]["product_name"] == root.name
    assert output["messages"][-1]["usage"] is None


def test_mentions_expand_context_and_preserve_citations(ask_db, monkeypatch):
    db = ask_db
    note = models.Note(org_id=db.test_org, workspace_id=db.test_workspace, title="Deployment Plan", slug="deployment-plan", body="Use SAML federation.")
    private = models.Note(org_id=db.test_org, workspace_id=db.test_other, title="Other Secret", slug="other-secret", body="PRIVATE")
    db.add_all([note, private])
    product = _product(db)
    monkeypatch.setattr(service, "run_search", lambda *_a, **_k: SimpleNamespace(hits=[]))
    monkeypatch.setattr(service.map_lookup, "expand", lambda *_a, **_k: SimpleNamespace(as_lines=lambda: [], neighbour_names=[]))
    monkeypatch.setattr(service, "_parent_passages", lambda *_: {})
    prepared = service._prepare_context(db, owner_principal(db.test_org),
        f'Explain @note:"Deployment Plan" @product:{product.slug} @connector:brave @web:docs.example/API @note:other-secret',
        workspace_id=db.test_workspace)
    assert len(prepared.chunks) == 2
    assert [c["index"] for c in prepared.chunks] == [1, 2]
    assert "SAML federation" in prepared.chunks[0]["fenced_text"]
    assert "Supports SAML federation" in prepared.chunks[1]["fenced_text"]
    assert "PRIVATE" not in str(prepared.chunks)
    assert [s.origin for s in prepared.sources] == ["note", "catalog"]
    assert prepared.prioritized_connectors == ["brave"]
    assert prepared.target_web_urls == ["https://docs.example/API"]


def test_targeted_web_uses_safe_reader_without_search(monkeypatch):
    from app.retrieval.web import WebFallback, WebPassage
    def gather(query, search_fn):
        assert search_fn(query) == [{"url": "https://docs.example/API", "title": "https://docs.example/API"}]
        return WebFallback(passages=[WebPassage(url="https://docs.example/API", title="Docs", text="Use SAML")])
    monkeypatch.setattr(service, "gather_web_fallback", gather)
    prepared = service.PreparedContext(chunks=[], sources=[], relationships_block="", needs_web=False,
        search_query="test", target_web_urls=["https://docs.example/API"])
    assert not service._attach_web(prepared, web_search=False).chunks
    result = service._attach_web(prepared)
    assert result.sources[0].source_url == "https://docs.example/API"
    assert "Use SAML" in result.chunks[0]["fenced_text"]


def test_graph_sync_reports_real_integrity_fields(ask_db, monkeypatch):
    monkeypatch.setattr("app.generation.handlers._sync_code_graph", lambda _: "Code knowledge graph synchronized.")
    result = handle_slash_command(ask_db, ask_db.test_workspace, owner_principal(ask_db.test_org), "/graphify-sync")
    assert result.handled
    assert "Relationships Awaiting Review" in result.text
    assert "Catalog status refreshed" in result.text


def test_connector_mentions_enable_only_authorized_requested_tools(generation_harness, monkeypatch):
    from app.tools.schema import ToolDefinition
    kwargs, _ = generation_harness
    monkeypatch.setattr(service, "_prepare_context", lambda *_a, **_k: service.PreparedContext(
        chunks=[], sources=[], relationships_block="", needs_web=False, search_query="test", prioritized_connectors=["ms365"]))
    definitions = [ToolDefinition(name=name, description=name, parameters={}) for name in
                   ("tool_list_notes", "mcp_brave_web_search", "mcp_ms365_search_mail")]
    monkeypatch.setattr("app.tools.registry.default_definitions", lambda _: definitions)
    loop = Mock(return_value=GroundedAnswer(text="Mail answer", citations=[], model_id="test", prompt_version="test"))
    monkeypatch.setattr("app.tools.loop.run_tool_loop", loop)
    answer = list(service.ask_stream(**kwargs, question="Find mail @connector:ms365"))[-1]
    assert answer.done
    assert [t.name for t in loop.call_args.kwargs["tools"]] == ["tool_list_notes", "mcp_ms365_search_mail"]
    assert "Requested connectors: ms365" in loop.call_args.args[1]


def test_code_graph_sync_uses_fixed_command_and_admin_access(monkeypatch):
    from app.generation.handlers import _sync_code_graph
    run = Mock(return_value=SimpleNamespace(returncode=0))
    monkeypatch.setattr("app.generation.handlers.subprocess.run", run)
    principal = _make_principal()
    assert "administrator" in _sync_code_graph(principal)
    run.assert_not_called()
    assert "synchronized" in _sync_code_graph(owner_principal(principal.org_id))
    assert run.call_args.args[0][1:] == ["-m", "graphify", "update", "."]
    assert "shell" not in run.call_args.kwargs
    assert run.call_args.kwargs["timeout"] == 30
    run.return_value.returncode = 1
    assert "unavailable" in _sync_code_graph(owner_principal(principal.org_id))
