"""4.4 Notebooks scope sources, notes, chat, and the customer brief."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import (
    AccessGrant,
    AuditLog,
    AgentAction,
    Base,
    Conversation,
    Document,
    Note,
    NoteLink,
    Notebook,
    NotebookSource,
    Organization,
    Product,
    Workspace,
)
from app.db.session import get_db
from app.main import app
from app.notebooks.service import EMPTY_SCOPE_ID
from app.security.jwt import mint_token
from app.security.labels import Role

client = TestClient(app)


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):  # noqa: ARG001
    return "JSON"


def _engine():
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _tables():
    return [
        Organization.__table__,
        AccessGrant.__table__,
        Workspace.__table__,
        Document.__table__,
        Notebook.__table__,
        NotebookSource.__table__,
        Note.__table__,
        NoteLink.__table__,
        Conversation.__table__,
        AuditLog.__table__,
        AgentAction.__table__,
        Product.__table__,
    ]


@pytest.fixture
def nb_db():
    engine = _engine()
    Base.metadata.create_all(engine, tables=_tables())
    SessionClass = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = SessionClass()
    org_a = Organization(id=uuid.uuid4(), slug="nb-a", name="A")
    org_b = Organization(id=uuid.uuid4(), slug="nb-b", name="B")
    db.add_all([org_a, org_b])
    db.flush()
    ws_a = Workspace(id=uuid.uuid4(), org_id=org_a.id, name="A workspace")
    ws_b = Workspace(id=uuid.uuid4(), org_id=org_b.id, name="B workspace")
    db.add_all([ws_a, ws_b])
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
    db.ws_a_id = ws_a.id
    yield db
    app.dependency_overrides.pop(get_db, None)
    db.close()


def _auth(org_id: uuid.UUID) -> dict:
    token = mint_token(org_id=org_id, user_id=uuid.uuid4(), role=Role.SOLUTIONS_ENGINEER)
    return {"Authorization": f"Bearer {token}"}


def _document(db, *, org_id, workspace_id, name: str, demo: bool = False) -> Document:
    document = Document(
        id=uuid.uuid4(),
        org_id=org_id,
        workspace_id=workspace_id,
        filename=name,
        original_filename=name,
        file_type="pdf",
        storage_key=f"sources/{name}",
        file_size=100,
        title=name,
        is_demo=demo,
        is_current=True,
    )
    db.add(document)
    db.commit()
    return document


def test_create_list_rename_and_reject_duplicate(nb_db):
    headers = _auth(nb_db.org_a_id)
    created = client.post("/notebooks", headers=headers, json={"name": "Northwind"})
    assert created.status_code == 201, created.text
    notebook_id = created.json()["id"]

    listed = client.get("/notebooks", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    renamed = client.patch(f"/notebooks/{notebook_id}", headers=headers, json={"name": "Northwind deal"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Northwind deal"

    again = client.post("/notebooks", headers=headers, json={"name": "Northwind deal"})
    assert again.status_code == 409


def test_cross_org_notebook_is_hidden(nb_db):
    created = client.post("/notebooks", headers=_auth(nb_db.org_a_id), json={"name": "Secret deal"})
    notebook_id = created.json()["id"]
    other = client.get(f"/notebooks/{notebook_id}/sources", headers=_auth(nb_db.org_b_id))
    assert other.status_code == 404


def test_new_notebook_enables_real_sources_and_toggle_persists(nb_db):
    kept = _document(nb_db, org_id=nb_db.org_a_id, workspace_id=nb_db.ws_a_id, name="jabra.pdf")
    dropped = _document(nb_db, org_id=nb_db.org_a_id, workspace_id=nb_db.ws_a_id, name="shure.pdf")
    _document(nb_db, org_id=nb_db.org_a_id, workspace_id=nb_db.ws_a_id, name="sample.pdf", demo=True)
    headers = _auth(nb_db.org_a_id)
    created = client.post("/notebooks", headers=headers, json={"name": "Rooms"})
    notebook_id = created.json()["id"]

    sources = client.get(f"/notebooks/{notebook_id}/sources", headers=headers)
    assert sources.status_code == 200
    by_id = {row["document_id"]: row for row in sources.json()}
    assert set(by_id) == {str(kept.id), str(dropped.id)}
    assert by_id[str(kept.id)]["enabled"] is True
    assert by_id[str(dropped.id)]["enabled"] is True

    updated = client.put(
        f"/notebooks/{notebook_id}/sources",
        headers=headers,
        json={"document_ids": [str(kept.id)]},
    )
    assert updated.status_code == 200, updated.text
    flags = {row["document_id"]: row["enabled"] for row in updated.json()}
    assert flags[str(kept.id)] is True
    assert flags[str(dropped.id)] is False

    again = client.get(f"/notebooks/{notebook_id}/sources", headers=headers)
    flags = {row["document_id"]: row["enabled"] for row in again.json()}
    assert flags[str(dropped.id)] is False


def test_ask_receives_only_enabled_source_ids(nb_db, monkeypatch):
    kept = _document(nb_db, org_id=nb_db.org_a_id, workspace_id=nb_db.ws_a_id, name="poly.pdf")
    dropped = _document(nb_db, org_id=nb_db.org_a_id, workspace_id=nb_db.ws_a_id, name="huawei.pdf")
    headers = _auth(nb_db.org_a_id)
    notebook_id = client.post("/notebooks", headers=headers, json={"name": "Bundle"}).json()["id"]
    client.put(
        f"/notebooks/{notebook_id}/sources",
        headers=headers,
        json={"document_ids": [str(kept.id)]},
    )
    captured: dict = {}

    def fake_ask(db, **kwargs):
        captured["filters"] = kwargs.get("filters")
        captured["notebook_id"] = kwargs.get("notebook_id")
        return SimpleNamespace(
            text="From your documents, Poly fits.",
            citations=[],
            model_id="fake",
            prompt_version="4.2.0",
            refused=False,
            refusal_reason=None,
            usage=None,
            conversation_id=None,
            message_id=None,
            tool_calls=[],
            tool_results=[],
        )

    monkeypatch.setattr("app.api.routes.ask.generation_ask", fake_ask)
    response = client.post(
        "/ask",
        headers=headers,
        json={
            "question": "What can I add?",
            "notebook_id": notebook_id,
            "filters": {"document_ids": [str(dropped.id), str(uuid.uuid4())]},
            "enable_tools": False,
        },
    )
    assert response.status_code == 200, response.text
    assert captured["filters"]["document_ids"] == [str(kept.id)]
    assert captured["notebook_id"] == uuid.UUID(notebook_id)


def test_empty_notebook_does_not_search_the_whole_library(nb_db, monkeypatch):
    _document(nb_db, org_id=nb_db.org_a_id, workspace_id=nb_db.ws_a_id, name="poly.pdf")
    headers = _auth(nb_db.org_a_id)
    notebook_id = client.post("/notebooks", headers=headers, json={"name": "Empty"}).json()["id"]
    client.put(f"/notebooks/{notebook_id}/sources", headers=headers, json={"document_ids": []})
    captured: dict = {}

    def fake_ask(db, **kwargs):
        captured["filters"] = kwargs.get("filters")
        return SimpleNamespace(
            text="No matching documents were found.",
            citations=[],
            model_id="fake",
            prompt_version="4.2.0",
            refused=False,
            refusal_reason=None,
            usage=None,
            conversation_id=None,
            message_id=None,
            tool_calls=[],
            tool_results=[],
        )

    monkeypatch.setattr("app.api.routes.ask.generation_ask", fake_ask)
    response = client.post(
        "/ask",
        headers=headers,
        json={"question": "Anything?", "notebook_id": notebook_id, "enable_tools": False},
    )
    assert response.status_code == 200, response.text
    assert captured["filters"]["document_ids"] == [str(EMPTY_SCOPE_ID)]


def test_ask_rejects_conversation_from_another_notebook(nb_db):
    headers = _auth(nb_db.org_a_id)
    first = client.post("/notebooks", headers=headers, json={"name": "First"}).json()["id"]
    second = client.post("/notebooks", headers=headers, json={"name": "Second"}).json()["id"]
    conversation = client.post(f"/conversations?notebook_id={first}", headers=headers).json()["id"]
    response = client.post("/ask", headers=headers, json={
        "question": "What is here?", "conversation_id": conversation, "notebook_id": second,
    })
    assert response.status_code == 404
    assert response.json()["detail"] == "Conversation not found"


def test_stream_reports_conversation_deleted_during_request(nb_db, monkeypatch):
    def stale(*args, **kwargs):
        raise ValueError("Conversation deleted-id not found")
        yield  # pragma: no cover - keep this a generator

    monkeypatch.setattr("app.api.routes.ask.generation_ask_stream", stale)
    response = client.post("/ask", headers=_auth(nb_db.org_a_id),
        json={"question": "What changed?", "stream": True})
    assert response.status_code == 200
    assert '"status_code": 404' in response.text


def test_agent_delete_note_requires_confirmation_and_is_idempotent(nb_db):
    from app.security.principal import owner_principal
    from app.tools.registry import ToolContext, execute_tool
    from app.tools.schema import ToolCall

    note = Note(org_id=nb_db.org_a_id, workspace_id=nb_db.ws_a_id,
                title="Draft", slug="draft", body="internal")
    nb_db.add(note)
    nb_db.commit()
    note_id = note.id
    headers = _auth(nb_db.org_a_id)
    from app.security.jwt import decode_jwt
    # Use the same authenticated user for proposal and confirmation.
    principal = owner_principal(nb_db.org_a_id, uuid.UUID(decode_jwt(headers["Authorization"].split()[1])["sub"]))
    ctx = ToolContext(db=nb_db, principal=principal, workspace_id=nb_db.ws_a_id)
    result = execute_tool(ToolCall(id="1", name="tool_propose_delete_note",
                                   arguments={"note_id": str(note.id)}), ctx)
    assert result.error is None
    assert nb_db.get(Note, note.id) is not None
    action_id = result.content["pending_action"]["id"]
    first = client.post(f"/agent/actions/{action_id}/confirm", headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "confirmed"
    again = client.post(f"/agent/actions/{action_id}/confirm", headers=headers)
    assert again.status_code == 200
    nb_db.expire_all()
    assert nb_db.get(Note, note_id) is None


def test_agent_action_is_hidden_from_another_tenant(nb_db):
    from datetime import datetime, timedelta, timezone
    action = AgentAction(org_id=nb_db.org_a_id, workspace_id=nb_db.ws_a_id,
        kind="delete_note", arguments={"note_id": str(uuid.uuid4())}, status="pending",
        idempotency_key=uuid.uuid4().hex, expires_at=datetime.now(timezone.utc) + timedelta(minutes=15))
    nb_db.add(action)
    nb_db.commit()
    response = client.post(f"/agent/actions/{action.id}/confirm", headers=_auth(nb_db.org_b_id))
    assert response.status_code == 404


def test_agent_confirmation_rechecks_current_role(nb_db):
    user_id = uuid.uuid4()
    action = AgentAction(org_id=nb_db.org_a_id, workspace_id=nb_db.ws_a_id, user_id=user_id,
        kind="publish_product", arguments={"name": "Atlas Hub", "vendor": "Acme", "category": "Software"},
        status="pending", idempotency_key=uuid.uuid4().hex,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15))
    nb_db.add(action)
    nb_db.commit()
    token = mint_token(org_id=nb_db.org_a_id, user_id=user_id, role=Role.VIEWER)
    response = client.post(f"/agent/actions/{action.id}/confirm", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    assert nb_db.query(Product).count() == 0


def test_catalog_publish_requires_in_chat_confirmation(nb_db):
    from app.tools.registry import ToolContext, execute_tool
    from app.tools.schema import ToolCall
    from app.security.principal import owner_principal
    from app.security.jwt import decode_jwt

    headers = _auth(nb_db.org_a_id)
    user_id = uuid.UUID(decode_jwt(headers["Authorization"].split()[1])["sub"])
    ctx = ToolContext(db=nb_db, principal=owner_principal(nb_db.org_a_id, user_id),
                      workspace_id=nb_db.ws_a_id)
    proposal = execute_tool(ToolCall(id="publish", name="tool_propose_publish_product",
        arguments={"name": "Atlas Hub", "vendor": "Acme", "category": "Software"}), ctx)
    assert proposal.error is None
    assert nb_db.query(Product).count() == 0
    action_id = proposal.content["pending_action"]["id"]
    confirmed = client.post(f"/agent/actions/{action_id}/confirm", headers=headers)
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["result"]["name"] == "Atlas Hub"
    assert nb_db.query(Product).count() == 1


def test_note_brief_and_conversation_stay_inside_the_notebook(nb_db):
    headers = _auth(nb_db.org_a_id)
    notebook_id = client.post("/notebooks", headers=headers, json={"name": "Acme"}).json()["id"]
    other_id = client.post("/notebooks", headers=headers, json={"name": "Other"}).json()["id"]

    note = client.post(
        "/notes",
        headers=headers,
        json={"title": "Sizing", "body": "12 huddle rooms.", "notebook_id": notebook_id},
    )
    assert note.status_code == 201, note.text
    assert note.json()["notebook_id"] == notebook_id

    in_notebook = client.get(f"/notes?notebook_id={notebook_id}", headers=headers)
    assert in_notebook.json()["total"] == 1
    elsewhere = client.get(f"/notes?notebook_id={other_id}", headers=headers)
    assert elsewhere.json()["total"] == 0

    brief = client.post(
        "/advisor/brief",
        headers=headers,
        json={
            "requirements": "Northwind needs 12 huddle rooms on Microsoft Teams.",
            "save_as_note": True,
            "notebook_id": notebook_id,
        },
    )
    assert brief.status_code == 200, brief.text
    assert brief.json()["saved"] is True
    after_brief = client.get(f"/notes?notebook_id={notebook_id}", headers=headers)
    assert after_brief.json()["total"] == 2

    created = client.post(f"/conversations?notebook_id={notebook_id}", headers=headers)
    assert created.status_code == 201, created.text
    conversation_id = created.json()["id"]
    assert created.json()["notebook_id"] == notebook_id

    scoped = client.get(f"/conversations?notebook_id={notebook_id}", headers=headers)
    assert scoped.json()["total"] == 1
    other_threads = client.get(f"/conversations?notebook_id={other_id}", headers=headers)
    assert other_threads.json()["total"] == 0
    hidden = client.get(
        f"/conversations/{conversation_id}?notebook_id={other_id}", headers=headers
    )
    assert hidden.status_code == 404
