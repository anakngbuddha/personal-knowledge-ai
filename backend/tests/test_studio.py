"""4.5 Briefing, FAQ, compare, and suggested questions."""

from __future__ import annotations

import uuid

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
    Document,
    Note,
    NoteLink,
    Notebook,
    NotebookSource,
    Organization,
    Workspace,
)
from app.db.session import get_db
from app.llm.fake import FakeLLMProvider
from app.llm.prompts import PROMPT_VERSION
from app.main import app
from app.security.jwt import mint_token
from app.security.labels import Role
from app.studio.prompts import STUDIO_PROMPT_VERSION

client = TestClient(app)


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):  # noqa: ARG001
    return "JSON"


class CountingProvider(FakeLLMProvider):
    def __init__(self, reply: str | None = None):
        self.calls = 0
        self.reply = reply

    @property
    def model_id(self) -> str:
        return "stub-llm" if self.reply else "fake-llm-v1"

    def generate_grounded_answer(self, question, context_chunks, *, system_prompt, **kwargs):
        self.calls += 1
        if self.reply is None:
            return super().generate_grounded_answer(
                question, context_chunks, system_prompt=system_prompt, **kwargs
            )
        from types import SimpleNamespace

        return SimpleNamespace(text=self.reply)


@pytest.fixture
def studio_db(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Organization.__table__,
            AccessGrant.__table__,
            Workspace.__table__,
            Document.__table__,
            Notebook.__table__,
            NotebookSource.__table__,
            Note.__table__,
            NoteLink.__table__,
            AuditLog.__table__,
        ],
    )
    SessionClass = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = SessionClass()
    org = Organization(id=uuid.uuid4(), slug="studio", name="Studio")
    db.add(org)
    db.flush()
    workspace = Workspace(id=uuid.uuid4(), org_id=org.id, name="Desk")
    db.add(workspace)
    db.commit()
    provider = CountingProvider()
    monkeypatch.setattr("app.studio.service.get_llm_provider", lambda: provider)

    def _get_db():
        inner = SessionClass()
        try:
            yield inner
        finally:
            inner.close()

    app.dependency_overrides[get_db] = _get_db
    db.org_id = org.id
    db.workspace_id = workspace.id
    db.provider = provider
    yield db
    app.dependency_overrides.pop(get_db, None)
    db.close()


def _auth(org_id: uuid.UUID) -> dict:
    token = mint_token(org_id=org_id, user_id=uuid.uuid4(), role=Role.SOLUTIONS_ENGINEER)
    return {"Authorization": f"Bearer {token}"}


def _source(db, name: str, summary: str) -> Document:
    document = Document(
        id=uuid.uuid4(),
        org_id=db.org_id,
        workspace_id=db.workspace_id,
        filename=name,
        original_filename=name,
        file_type="pdf",
        storage_key=f"sources/{name}",
        file_size=20,
        title=name,
        summary=summary,
        key_facts=[{"label": "Platform", "value": "Microsoft Teams"}],
        is_current=True,
        is_demo=False,
    )
    db.add(document)
    db.commit()
    return document


def test_answer_prompt_version_is_unchanged():
    assert PROMPT_VERSION == "4.2.0"
    assert STUDIO_PROMPT_VERSION == "1.0.0"


def test_briefing_and_faq_from_one_source(studio_db):
    source = _source(studio_db, "Jabra PanaCast.pdf", "A video bar for huddle rooms.")
    headers = _auth(studio_db.org_id)
    briefing = client.post(
        "/studio/run",
        headers=headers,
        json={"kind": "briefing", "document_ids": [str(source.id)]},
    )
    assert briefing.status_code == 200, briefing.text
    assert "Jabra PanaCast.pdf" in briefing.json()["markdown"]
    assert "From your documents" in briefing.json()["markdown"]
    assert studio_db.provider.calls == 1

    faq = client.post(
        "/studio/run",
        headers=headers,
        json={"kind": "faq", "document_ids": [str(source.id)]},
    )
    assert faq.status_code == 200
    assert "From your documents (Jabra PanaCast.pdf)" in faq.json()["markdown"]


def test_compare_needs_two_sources_and_empty_selection_is_rejected(studio_db):
    source = _source(studio_db, "Poly.pdf", "A room bar.")
    headers = _auth(studio_db.org_id)
    one = client.post(
        "/studio/run", headers=headers, json={"kind": "compare", "document_ids": [str(source.id)]}
    )
    assert one.status_code == 400
    assert "two sources" in one.json()["detail"].lower()

    empty = client.post("/studio/run", headers=headers, json={"kind": "briefing", "document_ids": []})
    assert empty.status_code == 400
    assert "at least one" in empty.json()["detail"].lower()


def test_saved_note_is_scoped_to_the_notebook(studio_db):
    source = _source(studio_db, "Shure.pdf", "Ceiling microphones for a boardroom.")
    headers = _auth(studio_db.org_id)
    notebook_id = client.post("/notebooks", headers=headers, json={"name": "Boardroom"}).json()["id"]
    saved = client.post(
        "/studio/run",
        headers=headers,
        json={
            "kind": "briefing",
            "document_ids": [str(source.id)],
            "notebook_id": notebook_id,
            "save_as_note": True,
        },
    )
    assert saved.status_code == 200, saved.text
    note_id = saved.json()["note_id"]
    assert note_id
    listed = client.get(f"/notes?notebook_id={notebook_id}", headers=headers)
    assert listed.json()["total"] == 1
    assert listed.json()["notes"][0]["id"] == note_id


def test_suggested_questions_are_cached(studio_db, monkeypatch):
    source = _source(studio_db, "Huawei.pdf", "Backup and disaster recovery on Huawei Cloud.")
    provider = CountingProvider(reply='["What does backup cover?", "Which cloud region?"]')
    monkeypatch.setattr("app.studio.service.get_llm_provider", lambda: provider)
    headers = _auth(studio_db.org_id)
    first = client.get(f"/studio/questions?document_id={source.id}", headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["questions"] == ["What does backup cover?", "Which cloud region?"]
    second = client.get(f"/studio/questions?document_id={source.id}", headers=headers)
    assert second.json()["questions"] == first.json()["questions"]
    assert provider.calls == 1
