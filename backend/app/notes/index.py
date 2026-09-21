"""Embed saved notes so Ask can retrieve them like documents."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models import Document, DocumentChunk, DocumentStatus
from app.documents import injection
from app.documents.chunking import chunk_blocks
from app.documents.extraction import extract
from app.documents.metadata import DocumentMetadataIn
from app.embeddings.factory import get_embedding_provider
from app.security.labels import ApprovalState, SourceType

logger = get_logger(__name__)


def note_filename(note_id: uuid.UUID) -> str:
    return f"note:{note_id}.md"


def index_note(db: Session, note) -> Document | None:
    """Chunk and embed a note. Failures are logged; note save still succeeds."""
    try:
        filename = note_filename(note.id)
        document = db.scalars(
            select(Document).where(
                Document.workspace_id == note.workspace_id,
                Document.original_filename == filename,
            )
        ).first()
        payload = f"# {note.title}\n\n{note.body}".encode("utf-8")
        if document is None:
            from app.documents.service import create_document
            from app.security.principal import owner_principal

            document = create_document(
                db,
                principal=owner_principal(note.org_id, note.created_by),
                original_filename=filename,
                data=payload,
                mime_type="text/markdown",
                metadata=DocumentMetadataIn(
                    title=note.title,
                    source_type=SourceType.PASTE,
                    approval_state=ApprovalState.APPROVED,
                    vendor="Notes",
                ),
            )
        else:
            from app.storage.factory import get_storage

            get_storage().put(document.storage_key, payload, content_type="text/markdown")
            document.title = note.title
            document.file_size = len(payload)
            document.approval_state = ApprovalState.APPROVED
            db.commit()

        result = extract(payload, "md")
        chunks = chunk_blocks(result.blocks)
        db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete()
        provider = get_embedding_provider()
        texts = [injection.neutralize_fences(chunk.text) for chunk in chunks]
        vectors = provider.embed_documents(texts) if texts else []
        for chunk, text, vector in zip(chunks, texts, vectors, strict=True):
            db.add(
                DocumentChunk(
                    document_id=document.id,
                    org_id=document.org_id,
                    chunk_index=chunk.chunk_index,
                    text=text,
                    section_title=chunk.section_title,
                    heading_path=list(chunk.heading_path) or None,
                    start_offset=chunk.start_offset,
                    end_offset=chunk.end_offset,
                    embedding=vector,
                    chunk_metadata={
                        "source_filename": filename,
                        "citation": f"note:{note.slug}",
                        "note_id": str(note.id),
                        "embedding_model": provider.model_id,
                        "embedding_dimensions": provider.dimensions,
                    },
                )
            )
        document.chunk_count = len(chunks)
        document.status = DocumentStatus.READY
        document.doc_metadata = {**(document.doc_metadata or {}), "note_id": str(note.id), "source_kind": "note"}
        db.commit()
        return document
    except Exception:
        logger.exception("failed to index note %s", getattr(note, "id", None))
        db.rollback()
        return None


def drop_note_index(db: Session, note_id: uuid.UUID, workspace_id: uuid.UUID) -> None:
    document = db.scalars(
        select(Document).where(
            Document.workspace_id == workspace_id,
            Document.original_filename == note_filename(note_id),
        )
    ).first()
    if document is None:
        return
    from app.documents.service import delete_document

    delete_document(db, document)
