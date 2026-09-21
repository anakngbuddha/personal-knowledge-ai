"""Logical dump/restore drill. Proves tenant data can be snapshotted and rebuilt within SLA."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.db.models import (
    Base,
    FreshnessAlert,
    Note,
    NoteLink,
    Organization,
    RestoreDrill,
    RestoreDrillStatus,
    VendorSource,
    Workspace,
)

DRILL_MODELS = (Note, NoteLink, VendorSource, FreshnessAlert)


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(element, compiler, **kw):  # noqa: ARG001
    return "JSON"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _count(db: Session, model, org_id: uuid.UUID) -> int:
    if not hasattr(model, "org_id"):
        return 0
    return int(db.scalar(select(func.count()).select_from(model).where(model.org_id == org_id)) or 0)


def dump_tenant(db: Session, org_id: uuid.UUID) -> dict[str, Any]:
    """Serialize tenant-scoped rows needed to prove a restore round-trip."""
    notes = list(db.scalars(select(Note).where(Note.org_id == org_id)))
    links = list(db.scalars(select(NoteLink).where(NoteLink.org_id == org_id)))
    sources = list(db.scalars(select(VendorSource).where(VendorSource.org_id == org_id)))
    alerts = list(db.scalars(select(FreshnessAlert).where(FreshnessAlert.org_id == org_id)))
    org = db.get(Organization, org_id)
    workspaces = list(db.scalars(select(Workspace).where(Workspace.org_id == org_id)))
    payload = {
        "org": {"id": str(org_id), "slug": org.slug if org else "unknown", "name": org.name if org else "unknown"},
        "workspaces": [{"id": str(w.id), "name": w.name} for w in workspaces],
        "notes": [
            {
                "id": str(n.id),
                "workspace_id": str(n.workspace_id),
                "title": n.title,
                "slug": n.slug,
                "body": n.body,
                "created_by": str(n.created_by) if n.created_by else None,
            }
            for n in notes
        ],
        "note_links": [
            {
                "id": str(link.id),
                "note_id": str(link.note_id),
                "target_kind": link.target_kind,
                "target_ref": link.target_ref,
                "display_text": link.display_text,
                "resolved": link.resolved,
                "resolved_id": str(link.resolved_id) if link.resolved_id else None,
            }
            for link in links
        ],
        "vendor_sources": [
            {
                "id": str(s.id),
                "workspace_id": str(s.workspace_id),
                "label": s.label,
                "url": s.url,
                "status": s.status,
                "last_hash": s.last_hash,
            }
            for s in sources
        ],
        "freshness_alerts": [
            {
                "id": str(a.id),
                "vendor_source_id": str(a.vendor_source_id),
                "kind": a.kind,
                "previous_hash": a.previous_hash,
                "new_hash": a.new_hash,
            }
            for a in alerts
        ],
        "counts": {model.__tablename__: _count(db, model, org_id) for model in DRILL_MODELS},
    }
    # Prove the snapshot is JSON-serializable (the actual backup artifact).
    json.dumps(payload)
    return payload


def _scratch_session() -> Session:
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
            Note.__table__,
            NoteLink.__table__,
            VendorSource.__table__,
            FreshnessAlert.__table__,
        ],
    )
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


def restore_tenant(db: Session, payload: dict[str, Any]) -> dict[str, int]:
    org_info = payload["org"]
    org_id = uuid.UUID(org_info["id"])
    db.add(Organization(id=org_id, slug=org_info["slug"], name=org_info["name"]))
    for workspace in payload.get("workspaces") or []:
        db.add(
            Workspace(
                id=uuid.UUID(workspace["id"]),
                org_id=org_id,
                name=workspace["name"],
            )
        )
    for note in payload.get("notes") or []:
        db.add(
            Note(
                id=uuid.UUID(note["id"]),
                org_id=org_id,
                workspace_id=uuid.UUID(note["workspace_id"]),
                title=note["title"],
                slug=note["slug"],
                body=note["body"],
                created_by=uuid.UUID(note["created_by"]) if note.get("created_by") else None,
            )
        )
    for link in payload.get("note_links") or []:
        db.add(
            NoteLink(
                id=uuid.UUID(link["id"]),
                org_id=org_id,
                note_id=uuid.UUID(link["note_id"]),
                target_kind=link["target_kind"],
                target_ref=link["target_ref"],
                display_text=link.get("display_text"),
                resolved=bool(link.get("resolved")),
                resolved_id=uuid.UUID(link["resolved_id"]) if link.get("resolved_id") else None,
            )
        )
    for source in payload.get("vendor_sources") or []:
        db.add(
            VendorSource(
                id=uuid.UUID(source["id"]),
                org_id=org_id,
                workspace_id=uuid.UUID(source["workspace_id"]),
                label=source["label"],
                url=source["url"],
                status=source.get("status") or "pending",
                last_hash=source.get("last_hash"),
            )
        )
    for alert in payload.get("freshness_alerts") or []:
        db.add(
            FreshnessAlert(
                id=uuid.UUID(alert["id"]),
                org_id=org_id,
                vendor_source_id=uuid.UUID(alert["vendor_source_id"]),
                kind=alert["kind"],
                previous_hash=alert.get("previous_hash"),
                new_hash=alert.get("new_hash"),
            )
        )
    db.commit()
    return {
        "notes": _count(db, Note, org_id),
        "note_links": _count(db, NoteLink, org_id),
        "vendor_sources": _count(db, VendorSource, org_id),
        "freshness_alerts": _count(db, FreshnessAlert, org_id),
    }


def run_restore_drill(
    db: Session,
    *,
    org_id: uuid.UUID,
    triggered_by: uuid.UUID | None,
    sla_seconds: float | None = None,
) -> RestoreDrill:
    sla = float(sla_seconds if sla_seconds is not None else settings.restore_drill_sla_seconds)
    drill = RestoreDrill(
        org_id=org_id,
        status=RestoreDrillStatus.RUNNING,
        sla_seconds=sla,
        triggered_by=triggered_by,
        started_at=_now(),
    )
    db.add(drill)
    db.commit()
    db.refresh(drill)

    started = _now()
    try:
        payload = dump_tenant(db, org_id)
        before = payload["counts"]
        scratch = _scratch_session()
        try:
            after_restored = restore_tenant(scratch, payload)
        finally:
            scratch.close()
        expected = {
            "notes": before.get("notes", 0),
            "note_links": before.get("note_links", 0),
            "vendor_sources": before.get("vendor_sources", 0),
            "freshness_alerts": before.get("freshness_alerts", 0),
        }
        if after_restored != expected:
            raise RuntimeError(f"restore mismatch: expected {expected}, got {after_restored}")
        finished = _now()
        duration = (finished - started).total_seconds()
        within = duration <= sla
        drill.status = RestoreDrillStatus.SUCCEEDED if within else RestoreDrillStatus.FAILED
        drill.duration_seconds = duration
        drill.within_sla = within
        drill.row_counts_before = before
        drill.row_counts_after = after_restored
        drill.finished_at = finished
        if not within:
            drill.error_message = f"restore completed in {duration:.3f}s, exceeding SLA {sla:.1f}s"
    except Exception as exc:  # noqa: BLE001 - drills must always record an outcome
        finished = _now()
        drill.status = RestoreDrillStatus.FAILED
        drill.duration_seconds = (finished - started).total_seconds()
        drill.within_sla = False
        drill.finished_at = finished
        drill.error_message = f"{type(exc).__name__}: {exc}"[:2000]
    db.commit()
    db.refresh(drill)
    return drill
