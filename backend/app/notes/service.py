"""CRUD for tribal notes plus wikilink extraction and resolution."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.catalog.models import slugify
from app.core.config import settings
from app.core.errors import AppError
from app.db.models import Note, NoteLink, NoteLinkKind, Product
from app.notes.wikilinks import ParsedWikilink, extract_wikilinks


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _unique_slug(db: Session, workspace_id: uuid.UUID, title: str, slug: str | None) -> str:
    base = slugify(slug or title) or f"note-{uuid.uuid4().hex[:8]}"
    candidate = base
    n = 2
    while db.scalar(select(Note.id).where(Note.workspace_id == workspace_id, Note.slug == candidate)):
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def resolve_link(
    db: Session,
    *,
    org_id: uuid.UUID,
    workspace_id: uuid.UUID,
    parsed: ParsedWikilink,
) -> tuple[bool, uuid.UUID | None, str]:
    """Resolve a wikilink against products, accounts (string refs), or notes."""
    kind = parsed.kind
    ref = parsed.target_ref

    if kind == NoteLinkKind.PRODUCT or not parsed.prefixed:
        product = db.scalar(
            select(Product).where(
                Product.workspace_id == workspace_id,
                Product.org_id == org_id,
                Product.slug == ref,
            )
        )
        if product is not None:
            return True, product.id, NoteLinkKind.PRODUCT

    if kind == NoteLinkKind.NOTE or not parsed.prefixed:
        note = db.scalar(
            select(Note).where(
                Note.workspace_id == workspace_id,
                Note.org_id == org_id,
                Note.slug == ref,
            )
        )
        if note is not None:
            return True, note.id, NoteLinkKind.NOTE

    if kind == NoteLinkKind.ACCOUNT:
        # Accounts are native string refs (no CRM). A non-empty ref is valid.
        return True, None, NoteLinkKind.ACCOUNT

    if not parsed.prefixed:
        return False, None, NoteLinkKind.NOTE
    return False, None, kind


def sync_links(
    db: Session,
    note: Note,
) -> list[NoteLink]:
    parsed = extract_wikilinks(note.body)
    db.execute(delete(NoteLink).where(NoteLink.note_id == note.id))
    rows: list[NoteLink] = []
    for item in parsed:
        resolved, resolved_id, kind = resolve_link(
            db,
            org_id=note.org_id,
            workspace_id=note.workspace_id,
            parsed=item,
        )
        link = NoteLink(
            org_id=note.org_id,
            note_id=note.id,
            target_kind=kind,
            target_ref=item.target_ref,
            display_text=item.display_text,
            resolved=resolved,
            resolved_id=resolved_id,
        )
        db.add(link)
        rows.append(link)
    db.flush()
    return rows


def create_note(
    db: Session,
    *,
    org_id: uuid.UUID,
    workspace_id: uuid.UUID,
    title: str,
    body: str,
    slug: str | None = None,
    created_by: uuid.UUID | None = None,
    notebook_id: uuid.UUID | None = None,
) -> Note:
    title = title.strip()
    if not title:
        raise AppError(status_code=400, code="note_title_required", message="note title is required")
    if len(body) > settings.notes_max_body_chars:
        raise AppError(
            status_code=400,
            code="note_body_too_large",
            message=f"note body exceeds {settings.notes_max_body_chars} characters",
        )
    if notebook_id is not None:
        from app.notebooks.service import get_notebook

        notebook = get_notebook(db, org_id=org_id, notebook_id=notebook_id)
        if notebook.workspace_id != workspace_id:
            raise AppError(status_code=404, code="notebook_not_found", message="Notebook not found.")
    note = Note(
        org_id=org_id,
        workspace_id=workspace_id,
        notebook_id=notebook_id,
        title=title,
        slug=_unique_slug(db, workspace_id, title, slug),
        body=body,
        created_by=created_by,
        updated_at=_now(),
    )
    db.add(note)
    db.flush()
    sync_links(db, note)
    db.commit()
    db.refresh(note)
    from app.notes.index import index_note

    index_note(db, note)
    return get_note(db, org_id=org_id, note_id=note.id)


def update_note(
    db: Session,
    *,
    org_id: uuid.UUID,
    note_id: uuid.UUID,
    title: str | None = None,
    body: str | None = None,
) -> Note:
    note = get_note(db, org_id=org_id, note_id=note_id)
    if title is not None:
        title = title.strip()
        if not title:
            raise AppError(status_code=400, code="note_title_required", message="note title is required")
        note.title = title
    if body is not None:
        if len(body) > settings.notes_max_body_chars:
            raise AppError(
                status_code=400,
                code="note_body_too_large",
                message=f"note body exceeds {settings.notes_max_body_chars} characters",
            )
        note.body = body
    sync_links(db, note)
    db.commit()
    db.refresh(note)
    from app.notes.index import index_note

    index_note(db, note)
    return get_note(db, org_id=org_id, note_id=note.id)


def get_note(db: Session, *, org_id: uuid.UUID, note_id: uuid.UUID) -> Note:
    note = db.scalar(
        select(Note)
        .options(selectinload(Note.links))
        .where(Note.id == note_id, Note.org_id == org_id)
    )
    if note is None:
        raise AppError(status_code=404, code="note_not_found", message="note not found")
    return note


def delete_note(db: Session, *, org_id: uuid.UUID, note_id: uuid.UUID) -> None:
    note = get_note(db, org_id=org_id, note_id=note_id)
    from app.notes.index import drop_note_index

    drop_note_index(db, note.id, note.workspace_id)
    db.delete(note)
    db.commit()


def list_notes(
    db: Session,
    *,
    org_id: uuid.UUID,
    workspace_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
    search: str | None = None,
    notebook_id: uuid.UUID | None = None,
) -> tuple[list[Note], int]:
    filters = [Note.org_id == org_id, Note.workspace_id == workspace_id]
    if notebook_id is not None:
        from app.notebooks.service import get_notebook

        get_notebook(db, org_id=org_id, notebook_id=notebook_id)
        filters.append(Note.notebook_id == notebook_id)
    if search:
        like = f"%{search.strip()}%"
        filters.append((Note.title.ilike(like)) | (Note.body.ilike(like)) | (Note.slug.ilike(like)))
    total = db.scalar(select(func.count()).select_from(Note).where(*filters)) or 0
    rows = list(
        db.scalars(
            select(Note)
            .options(selectinload(Note.links))
            .where(*filters)
            .order_by(Note.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return rows, int(total)


def backlinks(
    db: Session,
    *,
    org_id: uuid.UUID,
    kind: str,
    target_ref: str,
) -> list[Note]:
    link_ids = select(NoteLink.note_id).where(
        NoteLink.org_id == org_id,
        NoteLink.target_kind == kind,
        NoteLink.target_ref == target_ref,
    )
    return list(
        db.scalars(
            select(Note)
            .options(selectinload(Note.links))
            .where(Note.org_id == org_id, Note.id.in_(link_ids))
            .order_by(Note.updated_at.desc())
        )
    )
