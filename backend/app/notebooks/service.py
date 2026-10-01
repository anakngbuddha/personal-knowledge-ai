"""Notebooks: a deal or customer inside one workspace.

Documents stay owned by the workspace. Membership is an on/off flag. Notes and
chats created while a notebook is open are stamped with it. Rows that predate
notebooks keep a null id and remain visible when no notebook is selected.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import AppError
from app.db.models import Document, Note, Notebook, NotebookSource
from app.notes.index import note_filename

# An empty on-set must not mean "search everything". Retrieval treats an empty
# document id list as "no filter", so a notebook with every source off asks
# against this id and matches nothing.
EMPTY_SCOPE_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clean_name(name: str) -> str:
    cleaned = " ".join(name.split())
    if not cleaned:
        raise AppError(status_code=400, code="notebook_name_required", message="Give the notebook a name.")
    if len(cleaned) > 120:
        raise AppError(
            status_code=400,
            code="notebook_name_too_long",
            message="Notebook names can be at most 120 characters.",
        )
    return cleaned


def is_note_document(document: Document) -> bool:
    return (document.original_filename or "").startswith("note:")


def listable_sources(db: Session, *, org_id: uuid.UUID, workspace_id: uuid.UUID) -> list[Document]:
    """Current sources a person can toggle. Sample files and indexed notes stay out."""
    rows = db.scalars(
        select(Document)
        .where(
            Document.org_id == org_id,
            Document.workspace_id == workspace_id,
            Document.is_current.is_(True),
            Document.is_demo.is_(False),
        )
        .order_by(Document.uploaded_at.desc())
    )
    return [row for row in rows if not is_note_document(row)]


def get_notebook(db: Session, *, org_id: uuid.UUID, notebook_id: uuid.UUID) -> Notebook:
    notebook = db.scalar(
        select(Notebook)
        .options(selectinload(Notebook.sources))
        .where(Notebook.id == notebook_id, Notebook.org_id == org_id)
    )
    if notebook is None:
        raise AppError(status_code=404, code="notebook_not_found", message="Notebook not found.")
    return notebook


def list_notebooks(
    db: Session,
    *,
    org_id: uuid.UUID,
    workspace_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Notebook], int]:
    filters = [Notebook.org_id == org_id, Notebook.workspace_id == workspace_id]
    total = db.scalar(select(func.count()).select_from(Notebook).where(*filters)) or 0
    rows = list(
        db.scalars(
            select(Notebook)
            .where(*filters)
            .order_by(Notebook.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return rows, int(total)


def create_notebook(
    db: Session,
    *,
    org_id: uuid.UUID,
    workspace_id: uuid.UUID,
    name: str,
) -> Notebook:
    cleaned = _clean_name(name)
    taken = db.scalar(
        select(Notebook.id).where(Notebook.workspace_id == workspace_id, Notebook.name == cleaned)
    )
    if taken is not None:
        raise AppError(
            status_code=409,
            code="notebook_name_taken",
            message="A notebook with that name already exists.",
        )
    notebook = Notebook(
        org_id=org_id,
        workspace_id=workspace_id,
        name=cleaned,
        updated_at=_now(),
    )
    db.add(notebook)
    db.flush()
    for document in listable_sources(db, org_id=org_id, workspace_id=workspace_id):
        db.add(
            NotebookSource(
                org_id=org_id,
                notebook_id=notebook.id,
                document_id=document.id,
                enabled=True,
            )
        )
    db.commit()
    return get_notebook(db, org_id=org_id, notebook_id=notebook.id)


def rename_notebook(
    db: Session,
    *,
    org_id: uuid.UUID,
    notebook_id: uuid.UUID,
    name: str,
) -> Notebook:
    notebook = get_notebook(db, org_id=org_id, notebook_id=notebook_id)
    cleaned = _clean_name(name)
    if cleaned != notebook.name:
        taken = db.scalar(
            select(Notebook.id).where(
                Notebook.workspace_id == notebook.workspace_id,
                Notebook.name == cleaned,
                Notebook.id != notebook.id,
            )
        )
        if taken is not None:
            raise AppError(
                status_code=409,
                code="notebook_name_taken",
                message="A notebook with that name already exists.",
            )
        notebook.name = cleaned
    notebook.updated_at = _now()
    db.commit()
    return get_notebook(db, org_id=org_id, notebook_id=notebook.id)


def delete_notebook(db: Session, *, org_id: uuid.UUID, notebook_id: uuid.UUID) -> None:
    notebook = get_notebook(db, org_id=org_id, notebook_id=notebook_id)
    db.delete(notebook)
    db.commit()


def source_membership(db: Session, *, org_id: uuid.UUID, notebook_id: uuid.UUID,
                      limit: int = 100, offset: int = 0) -> list[tuple[Document, bool]]:
    notebook = db.scalar(select(Notebook).where(Notebook.id == notebook_id, Notebook.org_id == org_id))
    if notebook is None:
        raise AppError("Notebook not found", status_code=404)
    stmt = select(Document, NotebookSource.enabled).outerjoin(NotebookSource, (
        (NotebookSource.document_id == Document.id) & (NotebookSource.notebook_id == notebook_id) & (NotebookSource.org_id == org_id)
    )).where(Document.org_id == org_id, Document.workspace_id == notebook.workspace_id,
             Document.is_current.is_(True), Document.is_demo.is_(False), ~Document.original_filename.startswith("note:"))
    rows = db.execute(stmt.order_by(Document.uploaded_at.desc(), Document.id).limit(max(1, min(limit, 100))).offset(max(0, offset)))
    return [(document, bool(enabled)) for document, enabled in rows]


def set_enabled_sources(
    db: Session,
    *,
    org_id: uuid.UUID,
    notebook_id: uuid.UUID,
    document_ids: list[uuid.UUID],
) -> list[tuple[Document, bool]]:
    notebook = get_notebook(db, org_id=org_id, notebook_id=notebook_id)
    allowed = {
        document.id: document
        for document in listable_sources(db, org_id=org_id, workspace_id=notebook.workspace_id)
    }
    unknown = [str(item) for item in document_ids if item not in allowed]
    if unknown:
        raise AppError(
            status_code=400,
            code="notebook_source_unknown",
            message="One of those sources is not in this workspace.",
        )
    wanted = set(document_ids)
    existing = {row.document_id: row for row in notebook.sources}
    for document_id, document in allowed.items():
        row = existing.get(document_id)
        if row is None:
            db.add(
                NotebookSource(
                    org_id=org_id,
                    notebook_id=notebook.id,
                    document_id=document.id,
                    enabled=document_id in wanted,
                )
            )
        else:
            row.enabled = document_id in wanted
    for document_id, row in existing.items():
        if document_id not in allowed:
            row.enabled = False
    notebook.updated_at = _now()
    db.commit()
    return source_membership(db, org_id=org_id, notebook_id=notebook.id)


def enable_document(
    db: Session,
    *,
    org_id: uuid.UUID,
    notebook_id: uuid.UUID,
    document_id: uuid.UUID,
) -> None:
    """Turn one workspace document on for a notebook without changing the others."""
    notebook = get_notebook(db, org_id=org_id, notebook_id=notebook_id)
    document = db.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.org_id == org_id,
            Document.workspace_id == notebook.workspace_id,
        )
    )
    if document is None:
        raise AppError(
            status_code=404,
            code="notebook_source_unknown",
            message="That source is not in this workspace.",
        )
    existing = next((row for row in notebook.sources if row.document_id == document_id), None)
    if existing is None:
        db.add(
            NotebookSource(
                org_id=org_id,
                notebook_id=notebook.id,
                document_id=document_id,
                enabled=True,
            )
        )
    else:
        existing.enabled = True
    notebook.updated_at = _now()
    db.commit()


def enabled_document_ids(db: Session, *, notebook: Notebook) -> list[uuid.UUID]:
    """Ids Ask should search: switched-on sources, plus notes saved in this notebook."""
    ids = [row.document_id for row in notebook.sources if row.enabled]
    note_ids = list(
        db.scalars(select(Note.id).where(Note.notebook_id == notebook.id, Note.org_id == notebook.org_id))
    )
    if note_ids:
        names = [note_filename(note_id) for note_id in note_ids]
        indexed = db.scalars(
            select(Document.id).where(
                Document.workspace_id == notebook.workspace_id,
                Document.original_filename.in_(names),
                Document.is_current.is_(True),
            )
        )
        ids.extend(indexed)
    unique = list(dict.fromkeys(ids))
    return unique or [EMPTY_SCOPE_ID]
