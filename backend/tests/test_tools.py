"""Phase 5a single-turn tool calling tests."""

from __future__ import annotations

import inspect
import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles

from app.db.models import (
    Base,
    Organization,
    Product,
    ProductEdge,
    ReferenceArchitecture,
    ReferenceArchitectureProduct,
    Workspace,
)
from app.llm.fake import FakeLLMProvider
from app.llm.prompts import SYSTEM_PROMPT
from app.security.principal import owner_principal
from app.tools.loop import run_tool_loop
from app.tools.registry import (
    CatalogImpactArgs,
    HybridSearchArgs,
    ToolContext,
    default_definitions,
    execute_tool,
)
from app.tools.schema import ToolCall


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
            Product.__table__,
            ProductEdge.__table__,
            ReferenceArchitecture.__table__,
            ReferenceArchitectureProduct.__table__,
        ],
    )
    SessionClass = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return SessionClass()


def test_fake_provider_emits_tool_call_for_conflict_question():
    provider = FakeLLMProvider()
    answer = provider.generate_grounded_answer(
        "What are the prerequisite conflicts if I deploy Apex Identity Broker?",
        [],
        system_prompt=SYSTEM_PROMPT,
        tools=default_definitions(),
    )
    assert answer.tool_calls
    names = {c.name for c in answer.tool_calls}
    assert "tool_catalog_impact" in names or "tool_detect_contradictions" in names


def test_tool_loop_executes_and_synthesizes():
    db = _session()
    org = Organization(id=uuid.uuid4(), slug="acme", name="Acme")
    db.add(org)
    db.commit()
    ws = Workspace(id=uuid.uuid4(), org_id=org.id, name="Default")
    db.add(ws)
    db.commit()
    product = Product(
        id=uuid.uuid4(),
        org_id=org.id,
        workspace_id=ws.id,
        name="Apex Identity Broker",
        slug="apex-identity-broker",
        vendor="Acme",
        ownership="own",
        category="Identity",
    )
    db.add(product)
    db.commit()

    principal = owner_principal(org.id)
    ctx = ToolContext(db=db, principal=principal, workspace_id=ws.id)

    def _execute(call: ToolCall):
        return execute_tool(call, ctx)

    provider = FakeLLMProvider()
    answer = run_tool_loop(
        provider,
        "What are the prerequisite conflicts if I deploy Apex Identity Broker?",
        [],
        system_prompt=SYSTEM_PROMPT,
        history=None,
        tools=default_definitions(),
        execute=_execute,
    )
    assert answer.tool_calls
    assert answer.tool_results
    assert "catalog tools" in answer.text.lower() or "Apex" in answer.text
    assert not any(r.error and r.error.startswith("unknown_tool") for r in answer.tool_results)


def test_unknown_tool_name_is_rejected():
    db = _session()
    org = Organization(id=uuid.uuid4(), slug="acme", name="Acme")
    db.add(org)
    db.commit()
    ws = Workspace(id=uuid.uuid4(), org_id=org.id, name="Default")
    db.add(ws)
    db.commit()
    ctx = ToolContext(db=db, principal=owner_principal(org.id), workspace_id=ws.id)
    result = execute_tool(
        ToolCall(id="x", name="tool_shell_exec", arguments={"cmd": "id"}),
        ctx,
    )
    assert result.error == "unknown_tool:tool_shell_exec"


def test_invalid_extra_json_fields_rejected():
    with pytest.raises(ValidationError):
        CatalogImpactArgs.model_validate({"product": "Apex", "extra": "nope"})
    with pytest.raises(ValidationError):
        HybridSearchArgs.model_validate({"query": "sso", "rm": "-rf"})


def test_workspace_agent_tools_exclude_account_settings_and_require_write_role():
    from app.security.principal import restricted_principal
    names = {tool.name for tool in default_definitions()}
    assert {"tool_create_note", "tool_create_requirements", "tool_create_unpriced_proposal",
            "tool_start_rfp", "tool_propose_delete_note"} <= names
    assert not any("credential" in name or "sso" in name or "settings" in name for name in names)
    ctx = ToolContext(db=None, principal=restricted_principal(uuid.uuid4()), workspace_id=uuid.uuid4())
    result = execute_tool(ToolCall(id="draft", name="tool_create_note",
        arguments={"title": "Private", "body": "content"}), ctx)
    assert "PermissionError" in (result.error or "")


def test_proposal_tool_refuses_priced_text(monkeypatch):
    import app.tools.workspace as workspace
    monkeypatch.setattr(workspace, "_create_note", lambda _ctx, _args: {"artifact": {"kind": "note"}})
    ctx = ToolContext(db=None, principal=owner_principal(uuid.uuid4()), workspace_id=uuid.uuid4())
    priced = execute_tool(ToolCall(id="priced", name="tool_create_unpriced_proposal",
        arguments={"title": "Quote", "body": "Total: $900"}), ctx)
    assert "unpriced" in (priced.error or "").lower()
    draft = execute_tool(ToolCall(id="draft", name="tool_create_unpriced_proposal",
        arguments={"title": "Proposal", "body": "Proposed scope and assumptions"}), ctx)
    assert draft.error is None


def test_tool_loop_supports_multiple_actions_before_answer():
    from app.llm.base import GroundedAnswer
    from app.tools.schema import ToolResult

    class Provider:
        def __init__(self):
            self.round = 0

        def generate_grounded_answer(self, *args, **kwargs):
            self.round += 1
            calls = ([ToolCall(id=str(self.round), name="tool_list_notes", arguments={"limit": 2})]
                     if self.round < 3 else [])
            return GroundedAnswer(text="Prepared from workspace notes", citations=[], model_id="fake",
                                  prompt_version="test", tool_calls=calls)

    provider = Provider()
    answer = run_tool_loop(provider, "Prepare a draft", [], system_prompt="test", history=None,
        tools=default_definitions(), execute=lambda call: ToolResult(id=call.id, name=call.name, content={"notes": []}),
        max_rounds=4)
    assert provider.round == 3
    assert len(answer.tool_results) == 2


def test_expert_answer_prompt_keeps_sources_and_general_guidance_separate():
    from app.generation.claim_support import GENERAL_GUIDANCE_HEADING
    from app.llm.prompts import system_prompt_for
    expert = system_prompt_for(enable_tools=True, strict_mode=False)
    strict = system_prompt_for(enable_tools=False, strict_mode=True)
    assert "Check sources first" in expert
    assert GENERAL_GUIDANCE_HEADING in expert
    assert "ONLY from the provided context" in strict
    assert "Never invent products" in strict


def test_no_dangerous_execution_in_tools_package():
    import app.tools.loop as loop_mod
    import app.tools.registry as registry_mod

    for module in (loop_mod, registry_mod):
        source = inspect.getsource(module)
        for token in ("subprocess", "os.system", "eval(", "exec(", "shutil.rmtree"):
            assert token not in source, f"{module.__name__} contains {token}"


def test_phase3_path_unchanged_without_tools():
    provider = FakeLLMProvider()
    answer = provider.generate_grounded_answer(
        "What SSO protocols are supported?",
        [
            {
                "index": 1,
                "fenced_text": "SAML",
                "citation": "Guide p.1",
                "metadata": {"chunk_id": "c1", "document_id": "d1"},
            }
        ],
        system_prompt=SYSTEM_PROMPT,
    )
    assert not answer.tool_calls
    assert "[source_1]" in answer.text
