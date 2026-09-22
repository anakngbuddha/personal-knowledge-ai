"""4.4 Notebooks scope sources, notes, chat, and the customer brief."""

from __future__ import annotations

import uuid
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
    Base,
    Conversation,
    Document,
    Note,
    NoteLink,
    Notebook,
    NotebookSource,
    Organization,
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
