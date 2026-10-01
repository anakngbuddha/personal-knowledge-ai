"""Conversation and message management tests for Phase 3."""

import uuid
from datetime import datetime
import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base, Conversation, Message, Organization, Workspace
from app.generation.conversations import (
    add_message,
    auto_title,
    create_conversation,
    delete_conversation,
    get_conversation,
    get_history,
    list_conversations,
)
from app.api.routes.ask import get_conversation_sources_endpoint
from app.security.principal import owner_principal

# Teach SQLite how to render JSONB for test execution
@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    return "JSON"


@pytest.fixture
def sqlite_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Organization.__table__,
            Workspace.__table__,
            Conversation.__table__,
            Message.__table__,
        ],
    )
    SessionClass = sessionmaker(bind=engine)
    session = SessionClass()

    org = Organization(id=uuid.uuid4(), slug=f"test-org-{uuid.uuid4().hex[:8]}", name="Test Org")
    session.add(org)
    session.commit()

    ws1 = Workspace(id=uuid.uuid4(), org_id=org.id, name="Workspace 1")
    ws2 = Workspace(id=uuid.uuid4(), org_id=org.id, name="Workspace 2")
    session.add_all([ws1, ws2])
    session.commit()

    session.org_id = org.id
    session.ws1_id = ws1.id
    session.ws2_id = ws2.id

    try:
        yield session
    finally:
        session.close()


def test_conversation_crud_and_tenant_isolation(sqlite_session: Session):
    ws1 = sqlite_session.ws1_id
    ws2 = sqlite_session.ws2_id

    # Create conversation in ws1
    conv1 = create_conversation(sqlite_session, workspace_id=ws1, title="Onboarding")
    assert conv1.id is not None
    assert conv1.workspace_id == ws1
    assert conv1.title == "Onboarding"

    # Fetch conversation
    fetched = get_conversation(sqlite_session, conversation_id=conv1.id, workspace_id=ws1)
    assert fetched is not None
    assert fetched.id == conv1.id

    # Tenant isolation: ws2 cannot access conv1
    isolated = get_conversation(sqlite_session, conversation_id=conv1.id, workspace_id=ws2)
    assert isolated is None

    # List conversations for ws1
    convs, total = list_conversations(sqlite_session, workspace_id=ws1)
    assert total == 1
    assert len(convs) == 1
    assert convs[0].id == conv1.id

    # List conversations for ws2
    convs_ws2, total_ws2 = list_conversations(sqlite_session, workspace_id=ws2)
    assert total_ws2 == 0
    assert len(convs_ws2) == 0

    # Delete conversation
    deleted = delete_conversation(sqlite_session, conversation_id=conv1.id, workspace_id=ws1)
    assert deleted is True
    assert get_conversation(sqlite_session, conversation_id=conv1.id, workspace_id=ws1) is None


def test_add_message_and_history(sqlite_session: Session):
    ws1 = sqlite_session.ws1_id
    conv = create_conversation(sqlite_session, workspace_id=ws1)

    msg1 = add_message(
        sqlite_session,
        conversation_id=conv.id,
        role="user",
        content="What is the architecture?",
    )
    assert msg1.id is not None
    assert msg1.conversation_id == conv.id
    assert msg1.role == "user"

    msg2 = add_message(
        sqlite_session,
        conversation_id=conv.id,
        role="assistant",
        content="It is a hybrid RAG system [source_1].",
        citations=[{"chunk_id": "c1", "citation": "Arch doc p. 1"}],
        sources=[{"chunk_id": "c1", "citation": "Arch doc p. 1"}],
        usage={"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
        prompt_version="3.0.0",
        refused=False,
        model_id="fake-llm",
    )
    assert msg2.id is not None
    assert msg2.role == "assistant"
    assert msg2.prompt_version == "3.0.0"

    # Test get_history
    history = get_history(sqlite_session, conversation_id=conv.id)
    assert len(history) == 2
    assert history[0] == {"role": "user", "content": "What is the architecture?"}
    assert history[1] == {"role": "assistant", "content": "It is a hybrid RAG system [source_1]."}


def test_history_truncation(sqlite_session: Session):
    ws1 = sqlite_session.ws1_id
    conv = create_conversation(sqlite_session, workspace_id=ws1)

    # Add 6 turns (12 messages)
    for i in range(6):
        add_message(sqlite_session, conversation_id=conv.id, role="user", content=f"Q{i}")
        add_message(sqlite_session, conversation_id=conv.id, role="assistant", content=f"A{i}")

    # Truncate at max_turns=2 (4 messages)
    history = get_history(sqlite_session, conversation_id=conv.id, max_turns=2)
    assert len(history) == 4
    assert history[0]["content"] == "Q4"
    assert history[-1]["content"] == "A5"


def test_auto_title(sqlite_session: Session):
    ws1 = sqlite_session.ws1_id
    conv = create_conversation(sqlite_session, workspace_id=ws1, title=None)
    assert conv.title is None

    auto_title(sqlite_session, conversation_id=conv.id, question="What are the SLA tiers?")
    refreshed = get_conversation(sqlite_session, conversation_id=conv.id, workspace_id=ws1)
    assert refreshed.title == "What are the SLA tiers?"

    # Title is not overwritten if already set
    auto_title(sqlite_session, conversation_id=conv.id, question="Another question")
    refreshed = get_conversation(sqlite_session, conversation_id=conv.id, workspace_id=ws1)
    assert refreshed.title == "What are the SLA tiers?"


def test_conversation_sources_aggregation(sqlite_session: Session):
    ws1 = sqlite_session.ws1_id
    conv = create_conversation(sqlite_session, workspace_id=ws1)

    # Turn 1
    add_message(
        sqlite_session,
        conversation_id=conv.id,
        role="assistant",
        content="Answer 1",
        sources=[
            {"chunk_id": "c1", "document_id": "d1", "citation": "Doc 1 p. 1"},
            {"chunk_id": "c2", "document_id": "d1", "citation": "Doc 1 p. 2"},
        ],
    )
    # Turn 2 - has c2 again and new c3
    add_message(
        sqlite_session,
        conversation_id=conv.id,
        role="assistant",
        content="Answer 2",
        sources=[
            {"chunk_id": "c2", "document_id": "d1", "citation": "Doc 1 p. 2"},
            {"chunk_id": "c3", "document_id": "d2", "citation": "Doc 2 slide 5"},
        ],
    )

    conv_fetched = get_conversation(
        sqlite_session, conversation_id=conv.id, workspace_id=ws1
    )
    assert conv_fetched is not None
    seen_chunks = set()
    aggregated = []
    for msg in conv_fetched.messages:
        for s in (msg.sources or []):
            cid = s.get("chunk_id")
            if cid and cid not in seen_chunks:
                seen_chunks.add(cid)
                aggregated.append(s)

    assert len(aggregated) == 3
    assert {s["chunk_id"] for s in aggregated} == {"c1", "c2", "c3"}


def test_get_conversation_sources_endpoint_route(sqlite_session: Session):
    ws1 = sqlite_session.ws1_id
    conv = create_conversation(sqlite_session, workspace_id=ws1)
    principal = owner_principal(sqlite_session.org_id)

    add_message(
        sqlite_session,
        conversation_id=conv.id,
        role="assistant",
        content="Answer with source",
        sources=[
            {
                "chunk_id": "c10",
                "document_id": "d10",
                "document_title": "Datasheet",
                "citation": "Datasheet p. 4",
                "vendor": "Acme",
                "approval_state": "approved",
                "sensitivity": "internal",
                "is_stale": False,
            }
        ],
    )

    sources = get_conversation_sources_endpoint(
        conversation_id=str(conv.id),
        limit=100, offset=0,
        db=sqlite_session,
        principal=principal,
    )
    assert len(sources) == 1
    assert sources[0].chunk_id == "c10"
    assert sources[0].citation == "Datasheet p. 4"
    assert sources[0].vendor == "Acme"


def test_message_pages_are_bounded_and_preserve_order(sqlite_session):
    from app.api.routes.ask import get_conversation_endpoint
    conv = create_conversation(sqlite_session, workspace_id=sqlite_session.ws1_id, org_id=sqlite_session.org_id)
    for number in range(7):
        add_message(sqlite_session, conversation_id=conv.id, role="user", content=str(number))
    principal = owner_principal(sqlite_session.org_id)
    newest = get_conversation_endpoint(str(conv.id), notebook_id=None, limit=3, offset=0, db=sqlite_session, principal=principal)
    older = get_conversation_endpoint(str(conv.id), notebook_id=None, limit=3, offset=3, db=sqlite_session, principal=principal)
    assert [row.content for row in newest.messages] == ["4", "5", "6"]
    assert [row.content for row in older.messages] == ["1", "2", "3"]
    assert newest.message_total == older.message_total == 7
    from app.db.pagination import encode_cursor
    cursor = encode_cursor(datetime.fromisoformat(newest.messages[0].created_at), newest.messages[0].id)
    sought = get_conversation_endpoint(str(conv.id), notebook_id=None, limit=3, offset=0, cursor=cursor, db=sqlite_session, principal=principal)
    assert [row.content for row in sought.messages] == ["1", "2", "3"]
