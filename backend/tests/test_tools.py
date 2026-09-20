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
