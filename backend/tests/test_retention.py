"""Retention never deletes by default; holds, references, and tenant boundaries win."""
import os
import uuid
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import create_engine, event, select, func, text
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.ext.compiler import compiles
from app.db.models import Base, Organization, Document
from app.documents.service import create_document
from app.security.principal import owner_principal, Principal
from app.security import retention
from app.core.errors import AppError
from app.core.config import settings
from app.storage.local import LocalStorage

@compiles(JSONB, "sqlite")
def _json(element, compiler, **kwargs): return "JSON"

@compiles(TSVECTOR, "sqlite")
def _text(element, compiler, **kwargs): return "TEXT"

@pytest.fixture
def sample(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "local_storage_dir", str(tmp_path))
    monkeypatch.setattr(settings, "auto_approve_uploads", True)
    storage = LocalStorage()
    monkeypatch.setattr("app.documents.service.get_storage", lambda: storage)
    engine = create_engine("sqlite://")
    @event.listens_for(engine, "connect")
    def fk(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.create_function("to_tsvector", 2, lambda language, value: value or "", deterministic=True)
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        a = Organization(id=uuid.uuid4(), slug="retention-a", name="A")
        b = Organization(id=uuid.uuid4(), slug="retention-b", name="B")
        db.add_all([a, b]); db.commit()
        principals = [owner_principal(a.id), owner_principal(b.id)]
        documents = []
        for number, principal in enumerate(principals):
            doc = create_document(db, principal=principal, original_filename=f"fixture-{number}.txt", data=f"Fixture {number}".encode())
            doc.status = "ready"
            doc.uploaded_at = datetime.now(timezone.utc)-timedelta(days=100)
            documents.append(doc)
        db.commit()
        yield db, principals, documents, storage


def test_default_disabled_preview_and_tenant_purge(sample):
    db, principals, docs, storage = sample
    assert retention.purge(db, principals[0], dry_run=False)["deleted"] == 0
    policy = retention.set_policy(db, principals[0], periods={"document": 90})
    assert policy.enabled is False
    preview = retention.purge(db, principals[0])
    assert preview["candidates"] == [{"kind": "document", "id": str(docs[0].id)}]
    assert db.get(Document, docs[0].id) is not None
    assert retention.purge(db, principals[0], dry_run=False)["deleted"] == 0
    retention.set_policy(db, principals[0], periods={"document": 90}, enabled=True)
    result = retention.purge(db, principals[0], dry_run=False)
    assert result["deleted"] == 1
    assert db.get(Document, docs[1].id) is not None
    # Bytes survive DB deletion until the committed outbox is explicitly drained.
    assert storage.get(docs[0].storage_key) == b"Fixture 0"
    assert db.scalar(select(func.count()).select_from(retention.ObjectDeletion)) == 1
    assert retention.drain_object_deletions(db, principals[0], storage)["deleted"] == 1
    assert db.scalar(select(func.count()).select_from(retention.ObjectDeletion)) == 0
    assert retention.drain_object_deletions(db, principals[0], storage)["deleted"] == 0


def test_individual_and_tenant_legal_holds(sample):
    db, principals, docs, storage = sample
    retention.set_policy(db, principals[0], periods={"document": 1}, enabled=True)
    retention.add_hold(db, principals[0], "document", docs[0].id)
    assert retention.purge(db, principals[0], dry_run=False)["deleted"] == 0
    with pytest.raises(AppError) as exc:
        retention.add_hold(db, principals[0], "document", docs[1].id)
    assert exc.value.status_code == 404
    retention.set_policy(db, principals[1], periods={"document": 1}, enabled=True, legal_hold=True)
    assert retention.purge(db, principals[1], dry_run=False)["deleted"] == 0
    assert storage.get(docs[1].storage_key)


def test_referenced_document_and_outbox_rollback(sample):
    db, principals, docs, storage = sample
    db.execute(text("CREATE TABLE retention_test_ref (id text PRIMARY KEY, document_id char(32) REFERENCES documents(id) ON DELETE RESTRICT)"))
    db.execute(text("INSERT INTO retention_test_ref(id,document_id) VALUES (:id,:doc)"), {"id": "evidence", "doc": docs[0].id.hex})
    db.commit()
    retention.set_policy(db, principals[0], periods={"document": 1}, enabled=True)
    result = retention.purge(db, principals[0], dry_run=False)
    assert result["deleted"] == 0 and result["retained"] == 1
    assert db.get(Document, docs[0].id) is not None
    assert storage.get(docs[0].storage_key) == b"Fixture 0"
    assert db.scalar(select(func.count()).select_from(retention.ObjectDeletion)) == 0


def test_failed_cleanup_is_retryable_and_honors_new_hold(sample):
    db, principals, docs, storage = sample
    retention.set_policy(db, principals[0], periods={"document": 1}, enabled=True)
    retention.purge(db, principals[0], dry_run=False)
    class Offline:
        def delete(self, key): raise RuntimeError("offline fixture")
    assert retention.drain_object_deletions(db, principals[0], Offline())["pending"] == 1
    assert db.scalar(select(retention.ObjectDeletion)).attempts == 1
    retention.set_policy(db, principals[0], periods={"document": 1}, enabled=True, legal_hold=True)
    assert retention.drain_object_deletions(db, principals[0], storage)["deleted"] == 0
    assert storage.get(docs[0].storage_key)


def test_policy_cannot_target_immutable_evidence_and_requires_admin():
    principal = owner_principal(uuid.uuid4())
    for periods in ({"audit_log": 1}, {"quote": 1}, {"document": True}, {"document": 0}):
        with pytest.raises(AppError):
            retention.set_policy(None, principal, periods=periods, enabled=True)
    with pytest.raises(AppError) as exc:
        retention.purge(None, Principal(org_id=uuid.uuid4(), user_id=None, role="viewer"))
    assert exc.value.status_code == 403


def test_orphan_inventory_preserves_live_and_pending_objects(sample):
    db, principals, docs, storage = sample
    key = f"workspaces/{docs[0].workspace_id}/documents/{uuid.uuid4()}/orphan.txt"
    storage.put(key, b"orphan fixture")
    old = (datetime.now(timezone.utc)-timedelta(days=2)).timestamp()
    os.utime(storage._path(key), (old, old))
    os.utime(storage._path(docs[0].storage_key), (old, old))
    result = retention.orphan_inventory(db, principals[0], storage, docs[0].workspace_id, limit=500)
    assert [item["key"] for item in result["orphans"]] == [key]
    assert result["deletion_enabled"] is False
    with pytest.raises(AppError):
        retention.orphan_inventory(db, principals[1], storage, docs[0].workspace_id)
