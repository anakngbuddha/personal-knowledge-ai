"""Phase 1 ingestion pipeline.

upload -> R2 -> document row -> extract -> chunk -> embed -> persist (+ FTS)

A document is only marked `ready` when the source file is in object storage and its
chunks, embeddings, and full-text data all exist in PostgreSQL.
"""

import tempfile
import uuid
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import get_logger
from app.db.models import Document, DocumentChunk, DocumentStatus, Workspace
from app.db.session import SessionLocal
from app.documents import extraction
from app.documents.chunking import chunk_blocks
from app.embeddings.factory import get_embedding_provider
from app.storage.factory import get_storage

logger = get_logger(__name__)

DEFAULT_WORKSPACE_NAME = "My Knowledge"


def get_or_create_default_workspace(db: Session) -> Workspace:
    workspace = db.scalars(select(Workspace).order_by(Workspace.created_at)).first()
    if workspace is None:
        workspace = Workspace(name=DEFAULT_WORKSPACE_NAME)
        db.add(workspace)
        db.commit()
        db.refresh(workspace)
    return workspace


def create_document(
    db: Session,
    *,
    original_filename: str,
    data: bytes,
    mime_type: str | None,
) -> Document:
    file_type = extraction.detect_file_type(original_filename)
    workspace = get_or_create_default_workspace(db)

    document_id = uuid.uuid4()
    safe_name = Path(original_filename).name
    storage_key = f"workspaces/{workspace.id}/documents/{document_id}/{safe_name}"

    get_storage().put(storage_key, data, content_type=mime_type)

    document = Document(
        id=document_id,
        workspace_id=workspace.id,
        filename=safe_name,
        original_filename=original_filename,
        file_type=file_type,
        mime_type=mime_type,
        storage_key=storage_key,
        file_size=len(data),
        status=DocumentStatus.UPLOADED,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    logger.info("stored document %s (%s bytes) at %s", document.id, len(data), storage_key)
    return document


def process_document(document_id: uuid.UUID) -> None:
    """Run the full ingestion pipeline. Owns its own session so it is safe as a background task."""
    db = SessionLocal()
    temp_path: Path | None = None
    try:
        document = db.get(Document, document_id)
        if document is None:
            logger.warning("process_document: %s not found", document_id)
            return

        document.status = DocumentStatus.PROCESSING
        document.error_message = None
        db.commit()

        # Stream the source file out of object storage into a temp file. Render's disk is
        # temporary, so this file is deleted in the finally block.
        data = get_storage().get(document.storage_key)
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=f".{document.file_type}"
        ) as handle:
            handle.write(data)
            temp_path = Path(handle.name)
        del data

        result = extraction.extract(temp_path, document.file_type)
        chunks = chunk_blocks(result.blocks)
        if not chunks:
            raise AppError("chunking produced no chunks")

        provider = get_embedding_provider()
        db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete()
        db.commit()

        batch_size = max(1, settings.embedding_batch_size)
        stored = 0
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            vectors = provider.embed_documents([c.text for c in batch])
            for chunk, vector in zip(batch, vectors, strict=True):
                db.add(
                    DocumentChunk(
                        document_id=document.id,
                        chunk_index=chunk.chunk_index,
                        text=chunk.text,
                        page_number=chunk.page_number,
                        section_title=chunk.section_title,
                        start_offset=chunk.start_offset,
                        end_offset=chunk.end_offset,
                        embedding=vector,
                        chunk_metadata={
                            "source_filename": document.original_filename,
                            "embedding_model": provider.model_id,
                            "embedding_dimensions": provider.dimensions,
                            **result.metadata,
                        },
                    )
                )
            db.commit()
            stored += len(batch)
            logger.info("document %s: embedded %s/%s chunks", document.id, stored, len(chunks))

        document.chunk_count = stored
        document.page_count = result.page_count
        document.doc_metadata = result.metadata or None
        document.status = DocumentStatus.READY
        document.processed_at = datetime.now(timezone.utc)
        db.commit()
        logger.info("document %s ready with %s chunks", document.id, stored)
    except Exception as exc:  # noqa: BLE001 - failures must be visible on the document row
        db.rollback()
        logger.exception("ingestion failed for %s", document_id)
        document = db.get(Document, document_id)
        if document is not None:
            document.status = DocumentStatus.FAILED
            document.error_message = f"{type(exc).__name__}: {exc}"[:2000]
            db.commit()
    finally:
        if temp_path is not None:
            with suppress(OSError):
                temp_path.unlink()
        db.close()


def delete_document(db: Session, document: Document) -> None:
    with suppress(Exception):
        get_storage().delete(document.storage_key)
    db.delete(document)
    db.commit()
