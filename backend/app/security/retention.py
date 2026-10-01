"""Opt-in tenant retention, legal holds, and durable post-commit object cleanup."""
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import Boolean, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.exc import IntegrityError
from app.db.models import Base, Document, Conversation, Note, IngestionJob, TaskExecution, Organization, WorkflowRun, Workspace, Message
from sqlalchemy import cast, Text as SqlText, or_
from app.core.errors import AppError
from app.security.audit import record_audit


KINDS = {"document": (Document, "uploaded_at"), "conversation": (Conversation, "updated_at"), "note": (Note, "updated_at"), "ingestion_job": (IngestionJob, "updated_at"), "task_execution": (TaskExecution, "updated_at")}


def _document_referenced(db, org_id, document_id):
    return db.scalar(select(Message.id).join(Conversation, Conversation.id == Message.conversation_id).where(Conversation.org_id == org_id, or_(cast(Message.sources, SqlText).contains(str(document_id)), cast(Message.citations, SqlText).contains(str(document_id)))).limit(1)) is not None


class RetentionPolicy(Base):
    __tablename__ = "retention_policies"
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    legal_hold: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    periods: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class RetentionHold(Base):
    __tablename__ = "retention_holds"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    __table_args__ = (UniqueConstraint("org_id", "kind", "resource_id"),)


class ObjectDeletion(Base):
    __tablename__ = "retention_object_deletions"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


def require_admin(principal):
    if not principal.is_admin:
        raise AppError("administrator access required", status_code=403)


def set_policy(db, principal, *, periods, enabled=False, legal_hold=False):
    require_admin(principal)
    if not isinstance(periods, dict) or set(periods) - KINDS.keys() or any(type(value) is not int or not 1 <= value <= 36500 for value in periods.values()):
        raise AppError("invalid retention periods", status_code=422)
    if enabled and not periods:
        raise AppError("an enabled policy requires retention periods", status_code=422)
    db.scalar(select(Organization.id).where(Organization.id == principal.org_id).with_for_update())
    policy = db.get(RetentionPolicy, principal.org_id)
    if policy is None:
        policy = RetentionPolicy(org_id=principal.org_id)
        db.add(policy)
    policy.periods, policy.enabled, policy.legal_hold = dict(periods), enabled, legal_hold
    record_audit(db, principal, "retention_policy", "organization", str(principal.org_id), {"periods": periods, "enabled": enabled, "legal_hold": legal_hold})
    return policy


def add_hold(db, principal, kind, resource_id):
    require_admin(principal)
    if kind not in KINDS:
        raise AppError("invalid retention resource", status_code=422)
    # Same lock as purge/policy writes prevents a hold racing a deletion.
    db.scalar(select(Organization.id).where(Organization.id == principal.org_id).with_for_update())
    model = KINDS[kind][0]
    if not db.scalar(select(model.id).where(model.org_id == principal.org_id, model.id == resource_id)):
        raise AppError("retention resource not found", status_code=404)
    hold = db.scalar(select(RetentionHold).where(RetentionHold.org_id == principal.org_id, RetentionHold.kind == kind, RetentionHold.resource_id == resource_id))
    if hold is None:
        hold = RetentionHold(org_id=principal.org_id, kind=kind, resource_id=resource_id)
        db.add(hold)
    record_audit(db, principal, "retention_hold", kind, str(resource_id))
    return hold


def purge(db, principal, *, dry_run=True, batch_size=100):
    require_admin(principal)
    if not 1 <= batch_size <= 500:
        raise AppError("invalid retention batch size", status_code=422)
    db.scalar(select(Organization.id).where(Organization.id == principal.org_id).with_for_update())
    policy = db.get(RetentionPolicy, principal.org_id)
    result = {"dry_run": dry_run, "disabled": policy is None or not policy.enabled, "candidates": [], "deleted": 0, "retained": 0}
    if policy is None or policy.legal_hold or (not dry_run and not policy.enabled):
        return result
    now = datetime.now(timezone.utc)
    # Leaf execution records first; immutable audit/commercial evidence is excluded.
    for kind in ("task_execution", "ingestion_job", "note", "conversation", "document"):
        days = policy.periods.get(kind)
        if days is None:
            continue
        remaining = batch_size - len(result["candidates"])
        if remaining <= 0:
            break
        model, timestamp_name = KINDS[kind]
        held = select(RetentionHold.resource_id).where(RetentionHold.org_id == principal.org_id, RetentionHold.kind == kind)
        statement = select(model).where(model.org_id == principal.org_id, getattr(model, timestamp_name) < now - timedelta(days=days), model.id.not_in(held))
        if kind == "ingestion_job":
            statement = statement.where(model.status.in_(["succeeded", "dead"]))
        if kind == "task_execution":
            finished_runs = select(WorkflowRun.id).where(WorkflowRun.org_id == principal.org_id, WorkflowRun.status.in_(["succeeded", "failed"]))
            statement = statement.where(model.status.in_(["succeeded", "failed"]), model.workflow_run_id.in_(finished_runs))
        if kind == "document":
            statement = statement.where(model.status.not_in(["uploaded", "processing"]))
        rows = list(db.scalars(statement.order_by(getattr(model, timestamp_name), model.id).limit(remaining).with_for_update(skip_locked=True)))
        for row in rows:
            result["candidates"].append({"kind": kind, "id": str(row.id)})
            if dry_run:
                continue
            try:
                with db.begin_nested():
                    if kind == "note":
                        indexed = db.scalar(select(Document).where(Document.org_id == principal.org_id, Document.workspace_id == row.workspace_id, Document.original_filename == f"note:{row.id}.md"))
                        if indexed:
                            held_index = db.scalar(select(RetentionHold.id).where(RetentionHold.org_id == principal.org_id, RetentionHold.kind == "document", RetentionHold.resource_id == indexed.id))
                            if held_index or _document_referenced(db, principal.org_id, indexed.id):
                                result["retained"] += 1
                                continue
                            db.add(ObjectDeletion(org_id=principal.org_id, storage_key=indexed.storage_key))
                            db.delete(indexed)
                    if kind == "document":
                        if row.original_filename.startswith("note:"):
                            try:
                                note_id = uuid.UUID(row.original_filename.removeprefix("note:").removesuffix(".md"))
                            except ValueError:
                                note_id = None
                            if note_id and db.scalar(select(Note.id).where(Note.org_id == principal.org_id, Note.id == note_id)):
                                result["retained"] += 1
                                continue
                        held_jobs = select(RetentionHold.resource_id).where(RetentionHold.org_id == principal.org_id, RetentionHold.kind == "ingestion_job")
                        retained_child = db.scalar(select(IngestionJob.id).where(IngestionJob.org_id == principal.org_id, IngestionJob.document_id == row.id, IngestionJob.id.in_(held_jobs)).limit(1))
                        if retained_child or _document_referenced(db, principal.org_id, row.id):
                            result["retained"] += 1
                            continue
                        db.add(ObjectDeletion(org_id=principal.org_id, storage_key=row.storage_key))
                    db.delete(row)
                    db.flush()
                result["deleted"] += 1
            except IntegrityError:
                result["retained"] += 1
    record_audit(db, principal, "retention_preview" if dry_run else "retention_purge", "organization", str(principal.org_id), {"count": len(result["candidates"]), "deleted": result["deleted"], "retained": result["retained"]})
    return result


def drain_object_deletions(db, principal, storage, *, batch_size=100):
    require_admin(principal)
    if not 1 <= batch_size <= 500:
        raise AppError("invalid retention batch size", status_code=422)
    db.scalar(select(Organization.id).where(Organization.id == principal.org_id).with_for_update())
    # Deletion is deferred under a newly enabled tenant-wide legal hold.
    policy = db.get(RetentionPolicy, principal.org_id)
    if policy is None or not policy.enabled or policy.legal_hold:
        return {"deleted": 0, "pending": 0}
    rows = list(db.scalars(select(ObjectDeletion).where(ObjectDeletion.org_id == principal.org_id).order_by(ObjectDeletion.id).limit(batch_size).with_for_update(skip_locked=True)))
    deleted = 0
    for row in rows:
        parts = row.storage_key.split("/")
        try:
            workspace_id = uuid.UUID(parts[1]) if len(parts) >= 5 and parts[0] == "workspaces" and parts[2] == "documents" else None
        except ValueError:
            workspace_id = None
        if workspace_id is None or not db.scalar(select(Workspace.id).where(Workspace.id == workspace_id, Workspace.org_id == principal.org_id)):
            continue
        # Never erase bytes if a live document still references the key.
        if db.scalar(select(Document.id).where(Document.org_id == principal.org_id, Document.storage_key == row.storage_key).limit(1)):
            continue
        try:
            storage.delete(row.storage_key)
        except Exception:
            row.attempts += 1
            continue
        db.delete(row)
        deleted += 1
    record_audit(db, principal, "retention_objects", "organization", str(principal.org_id), {"deleted": deleted, "pending": len(rows)-deleted})
    return {"deleted": deleted, "pending": len(rows)-deleted}


def orphan_inventory(db, principal, storage, workspace_id, *, cursor=None, limit=100):
    require_admin(principal)
    if not 1 <= limit <= 500:
        raise AppError("invalid inventory limit", status_code=422)
    if not db.scalar(select(Workspace.id).where(Workspace.id == workspace_id, Workspace.org_id == principal.org_id)):
        raise AppError("workspace not found", status_code=404)
    prefix = f"workspaces/{workspace_id}/documents/"
    rows, next_cursor = storage.list_page(prefix, cursor, limit)
    keys = {row["key"] for row in rows if row["key"].startswith(prefix)}
    retained = set(db.scalars(select(Document.storage_key).where(Document.org_id == principal.org_id, Document.storage_key.in_(keys))))
    retained.update(db.scalars(select(ObjectDeletion.storage_key).where(ObjectDeletion.org_id == principal.org_id, ObjectDeletion.storage_key.in_(keys))))
    cutoff = datetime.now(timezone.utc) - timedelta(days=1)
    # Inventory is read-only: concurrent writes require a later reconciliation.
    return {"orphans": [{"key": row["key"], "modified": row["modified"].isoformat()} for row in rows if row["key"] in keys - retained and row["modified"] < cutoff], "next_cursor": next_cursor, "deletion_enabled": False}
