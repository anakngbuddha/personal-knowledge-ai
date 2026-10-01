"""Phase 10 tribal notes API + Phase 4.3 graph/wikilinks extensions."""

from __future__ import annotations

import re
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import Note, NoteLink, NoteLinkKind, Product, Conversation, Message
from app.db.session import get_db
from app.documents.service import get_or_create_default_workspace
from app.notes import service as notes
from app.security.audit import record_audit
from app.security.deps import resolve_principal
from app.security.principal import Principal

router = APIRouter(prefix="/notes", tags=["notes"])


class NoteLinkOut(BaseModel):
    target_kind: str
    target_ref: str
    display_text: str | None = None
    resolved: bool
    resolved_id: str | None = None


class NoteOut(BaseModel):
    id: str
    title: str
    slug: str
    body: str
    workspace_id: str
    notebook_id: str | None = None
    created_by: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    links: list[NoteLinkOut] = Field(default_factory=list)


class NoteListOut(BaseModel):
    notes: list[NoteOut]
    total: int
    limit: int
    offset: int


class NoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1, max_length=512)
    body: str = Field("", max_length=200_000)
    slug: str | None = Field(None, max_length=128)
    notebook_id: uuid.UUID | None = None


class NoteUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(None, min_length=1, max_length=512)
    body: str | None = Field(None, max_length=200_000)


class LinkTargetOut(BaseModel):
    kind: str
    ref: str
    title: str


class GraphNodeOut(BaseModel):
    id: str
    kind: str  # "note" | "product" | "account"
    title: str
    slug: str


class GraphEdgeOut(BaseModel):
    source_id: str
    source_kind: str
    target_id: str
    target_kind: str
    target_ref: str
    display_text: str | None = None
    resolved: bool


class GraphOut(BaseModel):
    nodes: list[GraphNodeOut]
    edges: list[GraphEdgeOut]


class SaveAnswerIn(BaseModel):
    message_id: Optional[str] = None
    text: Optional[str] = None
    citations: Optional[list[dict]] = None
    title: str = ""


def _http(exc: AppError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


def _serialize(note: Note) -> NoteOut:
    return NoteOut(
        id=str(note.id),
        title=note.title,
        slug=note.slug,
        body=note.body,
        workspace_id=str(note.workspace_id),
        notebook_id=str(note.notebook_id) if note.notebook_id else None,
        created_by=str(note.created_by) if note.created_by else None,
        created_at=note.created_at.isoformat() if note.created_at else None,
        updated_at=note.updated_at.isoformat() if note.updated_at else None,
        links=[
            NoteLinkOut(
                target_kind=link.target_kind,
                target_ref=link.target_ref,
                display_text=link.display_text,
                resolved=link.resolved,
                resolved_id=str(link.resolved_id) if link.resolved_id else None,
            )
            for link in note.links
        ],
    )


@router.get("", response_model=NoteListOut)
def list_notes_endpoint(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0, le=10000),
    search: str | None = Query(None, max_length=200),
    notebook_id: uuid.UUID | None = Query(None),
    cursor: str | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> NoteListOut:
    workspace = get_or_create_default_workspace(db, principal.org_id)
    try:
        rows, total = notes.list_notes(
            db,
            org_id=principal.org_id,
            workspace_id=workspace.id,
            limit=limit,
            offset=offset,
            search=search,
            notebook_id=notebook_id,
            cursor=cursor,
        )
    except AppError as exc:
        raise _http(exc) from exc
    return NoteListOut(
        notes=[_serialize(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=NoteOut, status_code=201)
def create_note_endpoint(
    payload: NoteIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> NoteOut:
    if not principal.can_write_catalog:
        raise HTTPException(status_code=403, detail="solutions engineer role required")
    workspace = get_or_create_default_workspace(db, principal.org_id)
    try:
        note = notes.create_note(
            db,
            org_id=principal.org_id,
            workspace_id=workspace.id,
            title=payload.title,
            body=payload.body,
            slug=payload.slug,
            created_by=principal.user_id,
            notebook_id=payload.notebook_id,
        )
    except AppError as exc:
        raise _http(exc) from exc
    record_audit(db, principal, "create", "note", str(note.id), {"slug": note.slug})
    return _serialize(note)


@router.get("/by-link/{kind}/{ref}", response_model=NoteListOut)
def notes_linking_to_endpoint(
    kind: str,
    ref: str,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0, le=10000),
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> NoteListOut:
    rows = notes.backlinks(db, org_id=principal.org_id, kind=kind, target_ref=ref, limit=limit, offset=offset)
    return NoteListOut(
        notes=[_serialize(row) for row in rows],
        total=notes.backlink_count(db, org_id=principal.org_id, kind=kind, target_ref=ref),
        limit=limit,
        offset=offset,
    )


@router.get("/link-targets", response_model=list[LinkTargetOut])
def link_targets_endpoint(
    q: str = Query("", min_length=0, max_length=100),
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> list[LinkTargetOut]:
    """Autocomplete for wikilink targets: products, notes."""
    workspace = get_or_create_default_workspace(db, principal.org_id)
    results: list[LinkTargetOut] = []

    # Search products
    if q:
        products = db.scalars(
            select(Product)
            .where(
                Product.org_id == principal.org_id,
                Product.workspace_id == workspace.id,
                (Product.name.ilike(f"%{q}%")) | (Product.slug.ilike(f"%{q}%")),
            )
            .limit(10)
        )
        for p in products:
            results.append(LinkTargetOut(kind="product", ref=p.slug, title=p.name))

    # Search notes
    if q:
        found_notes = db.scalars(
            select(Note)
            .where(
                Note.org_id == principal.org_id,
                Note.workspace_id == workspace.id,
                (Note.title.ilike(f"%{q}%")) | (Note.slug.ilike(f"%{q}%")),
            )
            .limit(10)
        )
        for n in found_notes:
            results.append(LinkTargetOut(kind="note", ref=n.slug, title=n.title))

    return results[:20]  # Cap total results


@router.get("/graph", response_model=GraphOut)
def graph_endpoint(
    node_limit: int = Query(200, ge=1, le=500),
    edge_limit: int = Query(500, ge=1, le=1000),
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> GraphOut:
    workspace = get_or_create_default_workspace(db, principal.org_id)
    note_rows = list(db.scalars(select(Note).where(Note.org_id == principal.org_id, Note.workspace_id == workspace.id).order_by(Note.id).limit(node_limit)))
    product_rows = list(db.scalars(select(Product).where(Product.org_id == principal.org_id, Product.workspace_id == workspace.id).order_by(Product.id).limit(node_limit - len(note_rows))))
    note_map = {n.id: n for n in note_rows}
    product_map = {p.id: p for p in product_rows}
    nodes = [GraphNodeOut(id=str(n.id), kind="note", title=n.title, slug=n.slug) for n in note_rows]
    nodes += [GraphNodeOut(id=str(p.id), kind="product", title=p.name, slug=p.slug) for p in product_rows]
    links = db.scalars(select(NoteLink).where(NoteLink.org_id == principal.org_id, NoteLink.note_id.in_(note_map)).order_by(NoteLink.id).limit(edge_limit))
    edges = []
    account_nodes = set()
    for link in links:
        if link.target_kind == NoteLinkKind.ACCOUNT and (principal.sees_all_accounts or link.target_ref in (principal.account_refs or ())):
            account_id = "account:" + link.target_ref
            if account_id not in account_nodes and len(nodes) < node_limit:
                account_nodes.add(account_id)
                nodes.append(GraphNodeOut(id=account_id, kind="account", title=link.target_ref))
            if account_id in account_nodes:
                edges.append(GraphEdgeOut(source_id=str(link.note_id), source_kind="note", target_id=account_id, target_kind="account", target_ref=link.target_ref, display_text=link.display_text, resolved=True))
            continue
        target = product_map.get(link.resolved_id) if link.target_kind == NoteLinkKind.PRODUCT else note_map.get(link.resolved_id) if link.target_kind == NoteLinkKind.NOTE else None
        if target is not None:
            edges.append(GraphEdgeOut(source_id=str(link.note_id), source_kind="note", target_id=str(target.id), target_kind=link.target_kind, target_ref=link.target_ref, display_text=link.display_text, resolved=link.resolved))
    return GraphOut(nodes=nodes, edges=edges)


@router.post("/from-answer", response_model=NoteOut, status_code=201)
def save_answer_as_note_endpoint(
    payload: SaveAnswerIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> NoteOut:
    """Save a chat message or raw text as a note."""
    if not principal.can_write_catalog:
        raise HTTPException(status_code=403, detail="solutions engineer role required")
    workspace = get_or_create_default_workspace(db, principal.org_id)
    text = ""
    title = payload.title or ""

    if payload.message_id:
        # Load from conversation message
        try:
            msg_uuid = uuid.UUID(payload.message_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid message ID") from None

        message = db.scalar(
            select(Message)
            .join(Conversation)
            .where(
                Message.id == msg_uuid,
                Conversation.org_id == principal.org_id,
                Conversation.workspace_id == workspace.id,
            )
        )
        if not message:
            raise HTTPException(status_code=404, detail="Message not found") from None
        text = message.content or ""
        if not title:
            title = _auto_title(text)
    elif payload.text:
        text = payload.text
        if not title:
            title = _auto_title(text)
    else:
        raise HTTPException(status_code=400, detail="Either message_id or text is required") from None

    if not title:
        title = "Untitled Note"

    # Include citations as a footer if provided
    if payload.citations:
        citations_md = "\n\n### Sources\n"
        for c in payload.citations:
            source = c.get("source") or c.get("chunk_id", "Unknown")
            citations_md += f"- {source}\n"
        text += citations_md

    try:
        note = notes.create_note(
            db,
            org_id=principal.org_id,
            workspace_id=workspace.id,
            title=title,
            body=text,
            created_by=principal.user_id,
        )
    except AppError as exc:
        raise _http(exc) from exc
    record_audit(db, principal, "create", "note", str(note.id), {"from_answer": True})
    return _serialize(note)


@router.get("/{note_id}", response_model=NoteOut)
def get_note_endpoint(
    note_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> NoteOut:
    try:
        note = notes.get_note(db, org_id=principal.org_id, note_id=note_id)
    except AppError as exc:
        raise _http(exc) from exc
    return _serialize(note)


@router.put("/{note_id}", response_model=NoteOut)
def update_note_endpoint(
    note_id: uuid.UUID,
    payload: NoteUpdateIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> NoteOut:
    if not principal.can_write_catalog:
        raise HTTPException(status_code=403, detail="solutions engineer role required")
    try:
        note = notes.update_note(
            db,
            org_id=principal.org_id,
            note_id=note_id,
            title=payload.title,
            body=payload.body,
        )
    except AppError as exc:
        raise _http(exc) from exc
    record_audit(db, principal, "update", "note", str(note.id), {"slug": note.slug})
    return _serialize(note)


@router.delete("/{note_id}", status_code=204)
def delete_note_endpoint(
    note_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> None:
    if not principal.can_write_catalog:
        raise HTTPException(status_code=403, detail="solutions engineer role required")
    try:
        notes.delete_note(db, org_id=principal.org_id, note_id=note_id)
    except AppError as exc:
        raise _http(exc) from exc
    record_audit(db, principal, "delete", "note", str(note_id))


def _auto_title(text: str, max_length: int = 80) -> str:
    """Generate a title from the first line of text."""
    lines = text.strip().split("\n")
    first = lines[0] if lines else ""
    # Remove markdown and clean up
    first = re.sub(r"^#+\s*", "", first)  # remove markdown headings
    first = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", first)  # inline links
    first = re.sub(r"[*_`]", "", first)  # bold, italic, code
    first = first.strip()
    if not first:
        return "Untitled Note"
    return first[:max_length].strip()
