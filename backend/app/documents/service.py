"""Phase 1 ingestion pipeline.

    upload -> sniff -> scan -> hash -> dedup / version -> object storage
           -> document row -> queued job
           -> extract -> understand -> chunk -> injection flags -> embed -> persist (+ FTS)
           -> read for the product map

A document is only `ready` when the source file is in object storage and its chunks,
embeddings, and full-text data all exist in PostgreSQL.

Changes from the previous build, all of them Phase 1 requirements:

* content sniffing and malware scanning happen **before** anything is stored
* deduplication by content hash, and versioning when a document is re-uploaded
* ingestion is queued in a durable table rather than an in-process task list
* the source file is never written to local disk, not even a temp file
* instruction-like passages are flagged per chunk and counted on the document

Added in 2.2: one understand pass per source, between extraction and ready. It is
advisory by construction. It cannot fail an upload, and only a confident reading is
allowed to fill vendor, products, or validity.

Added in 3.1: one map read per source, after ready. Also advisory. It only ever
proposes: new products arrive as suggestions and relationships wait for a person.
"""

from __future__ import annotations

import hashlib
import uuid
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError, DuplicateDocument
from app.core.logging import get_logger
from app.db.models import Document, DocumentChunk, DocumentStatus, Workspace
from app.db.session import SessionLocal, mark_system_session
from app.documents import extraction, injection
from app.documents.chunking import chunk_blocks
from app.documents.metadata import DocumentMetadataIn
from app.documents.scanning import scan_or_raise
from app.documents.sniffing import decide_file_type
from app.documents.understanding import apply_understanding, understand_source
from app.embeddings.factory import get_embedding_provider
from app.jobs import queue
from app.security.labels import ApprovalState
from app.security.principal import Principal
from app.storage.factory import get_storage

logger = get_logger(__name__)

DEFAULT_WORKSPACE_NAME = "My Knowledge"


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def get_or_create_default_workspace(db: Session, org_id: uuid.UUID | None = None) -> Workspace:
    statement = select(Workspace).order_by(Workspace.created_at)
    if org_id is not None:
        statement = statement.where(Workspace.org_id == org_id)
    workspace = db.scalars(statement).first()
    if workspace is None:
        workspace = Workspace(name=DEFAULT_WORKSPACE_NAME, org_id=org_id)
        db.add(workspace)
        db.commit()
        db.refresh(workspace)
    elif workspace.org_id is None and org_id is not None:
        workspace.org_id = org_id
        db.commit()
    return workspace


def find_duplicate(db: Session, workspace_id: uuid.UUID, digest: str) -> Document | None:
    return db.scalars(
        select(Document).where(
            Document.workspace_id == workspace_id,
            Document.content_hash == digest,
            Document.is_current.is_(True),
        )
    ).first()


def find_previous_version(
    db: Session, workspace_id: uuid.UUID, original_filename: str
) -> Document | None:
    return db.scalars(
        select(Document)
        .where(
            Document.workspace_id == workspace_id,
            Document.original_filename == original_filename,
            Document.is_current.is_(True),
        )
        .order_by(Document.version.desc())
    ).first()


def create_document(
    db: Session,
    *,
    principal: Principal,
    original_filename: str,
    data: bytes,
    mime_type: str | None = None,
    metadata: DocumentMetadataIn | None = None,
    allow_duplicate: bool = False,
    apply_auto_approve: bool = True,
    allow_incomplete_approval: bool = False,
    workspace_id: uuid.UUID | None = None,
) -> Document:
    """Validate, scan, store and register one document. Does not extract.

    ``apply_auto_approve=False`` keeps the caller's approval state. Client RFP
    intake uses that so an incoming requirements file stays draft even when
    uploads are auto-approved. ``allow_incomplete_approval`` is only for
    operator-chosen vendor crawls, which are approved without a curation form.
    """
    meta = metadata or DocumentMetadataIn()
    if apply_auto_approve and settings.auto_approve_uploads:
        meta = meta.model_copy(update={"approval_state": ApprovalState.APPROVED})
    elif not (allow_incomplete_approval and meta.approval_state == ApprovalState.APPROVED):
        promotion_error = meta.promotion_error()
        if promotion_error:
            raise AppError(promotion_error)

    decision = decide_file_type(original_filename, data, mime_type)
    # Scanning happens on the bytes we were actually given, before any parser,
    # before object storage, and before a row exists to be forgotten about.
    scan = scan_or_raise(data, decision.file_type)

    if workspace_id is None:
        workspace = get_or_create_default_workspace(db, principal.org_id)
    else:
        workspace = db.get(Workspace, workspace_id)
        if workspace is None or workspace.org_id != principal.org_id:
            raise AppError(
                status_code=404,
                code="workspace_not_found",
                message="workspace not found",
            )
    digest = content_hash(data)

    duplicate = find_duplicate(db, workspace.id, digest)
    if duplicate is not None and not allow_duplicate:
        raise DuplicateDocument(
            f"identical content already ingested as {duplicate.original_filename!r}",
            existing_id=duplicate.id,
        )

    previous = find_previous_version(db, workspace.id, original_filename)
    version = (previous.version + 1) if previous else 1

    document_id = uuid.uuid4()
    safe_name = Path(original_filename).name
    storage_key = f"workspaces/{workspace.id}/documents/{document_id}/{safe_name}"
    get_storage().put(storage_key, data, content_type=mime_type)

    missing = meta.missing_fields()
    document = Document(
        id=document_id,
        org_id=principal.org_id,
        workspace_id=workspace.id,
        filename=safe_name,
        original_filename=original_filename,
        file_type=decision.file_type,
        mime_type=decision.sniffed.detail,
        declared_mime_type=mime_type,
        storage_key=storage_key,
        file_size=len(data),
        content_hash=digest,
        title=meta.title or Path(original_filename).stem,
        source_type=meta.source_type,
        source_url=meta.source_url,
        source_of_truth_url=meta.source_of_truth_url,
        vendor=meta.vendor,
        ownership=meta.ownership,
        products_referenced=meta.products_referenced or None,
        account_ref=meta.account_ref,
        approval_state=meta.approval_state,
        sensitivity=meta.sensitivity,
        valid_until=meta.valid_until,
        metadata_complete=not missing,
        metadata_missing=missing or None,
        version=version,
        supersedes_id=previous.id if previous else None,
        status=DocumentStatus.UPLOADED,
        scan_result={**scan.as_dict(), "type_decision": decision.as_dict()},
    )
    db.add(document)

    if previous is not None:
        # The old version stays queryable for provenance but leaves the retrieval
        # corpus, so an answer can never cite a superseded datasheet.
        previous.is_current = False

    db.commit()
    db.refresh(document)
    logger.info(
        "stored document %s v%s (%s bytes, %s) at %s",
        document.id,
        document.version,
        len(data),
        document.file_type,
        storage_key,
    )
    return document


def enqueue_ingestion(db: Session, document: Document, *, user_initiated: bool = True) -> None:
    queue.enqueue(db, document_id=document.id, org_id=document.org_id, user_initiated=user_initiated)


def process_document(document_id: uuid.UUID) -> None:
    """Run extraction through persistence. Owns its own session: the worker calls it."""
    db = mark_system_session(SessionLocal())
    try:
        document = db.get(Document, document_id)
        if document is None:
            logger.warning("process_document: %s not found", document_id)
            return

        document.status = DocumentStatus.PROCESSING
        document.error_message = None
        db.commit()

        data = get_storage().get(document.storage_key)
        try:
            def _progress(message: str) -> None:
                extra = dict(document.doc_metadata or {})
                extra["progress"] = message
                document.doc_metadata = extra
                db.commit()

            result = extraction.extract(data, document.file_type, on_progress=_progress)
            chunks = chunk_blocks(result.blocks)
        finally:
            del data

        if not chunks:
            raise AppError("chunking produced no chunks")

        # 2.2 understand step. Never fatal: a source we could not summarize is still
        # searchable, and that is the reason it was uploaded.
        understanding = None
        if settings.document_understanding_enabled:
            _progress("Working out what this source says")
            understanding = understand_source(
                "\n\n".join(block.text for block in result.blocks if block.text),
                filename=document.original_filename,
            )

        provider = get_embedding_provider()
        db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete()
        db.commit()

        batch_size = max(1, settings.embedding_batch_size)
        stored = 0
        flagged = 0
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            # Fences are neutralised at ingest so the stored text and the prompted
            # text are identical. A chunk can never close its own fence later.
            texts = [injection.neutralize_fences(chunk.text) for chunk in batch]
            vectors = provider.embed_documents(texts)
            for chunk, text, vector in zip(batch, texts, vectors, strict=True):
                findings = injection.scan_for_injection(text)
                flagged += bool(findings)
                chunk_meta = {
                    "source_filename": document.original_filename,
                    "citation": chunk.anchor.label(),
                    "heading": chunk.heading,
                    "is_table": chunk.is_table,
                    "parent_index": chunk.parent_index,
                    "embedding_model": provider.model_id,
                    "embedding_dimensions": provider.dimensions,
                    **result.metadata,
                }
                if chunk.parent_text:
                    # 2.3: match the child, prompt the parent. Fences are neutralised
                    # here too, because this text also reaches the model.
                    chunk_meta["parent_text"] = injection.neutralize_fences(chunk.parent_text)
                db.add(
                    DocumentChunk(
                        document_id=document.id,
                        org_id=document.org_id,
                        chunk_index=chunk.chunk_index,
                        text=text,
                        page_number=chunk.page_number,
                        slide_number=chunk.slide_number,
                        sheet_name=chunk.sheet_name,
                        cell_range=chunk.cell_range,
                        section_title=chunk.section_title,
                        heading_path=list(chunk.heading_path) or None,
                        start_offset=chunk.start_offset,
                        end_offset=chunk.end_offset,
                        embedding=vector,
                        injection_flags=[f.as_dict() for f in findings] or None,
                        chunk_metadata=chunk_meta,
                    )
                )
            db.commit()
            stored += len(batch)
            logger.info("document %s: embedded %s/%s chunks", document.id, stored, len(chunks))

        document.chunk_count = stored
        document.page_count = result.page_count
        document.ocr_applied = result.ocr_applied
        document.injection_flag_count = flagged
        doc_meta = {**(result.metadata or {}), "warnings": result.warnings}
        if understanding is not None:
            apply_understanding(document, understanding)
            doc_meta["understanding"] = {
                "origin": understanding.origin,
                "confidence": understanding.confidence,
                "prompt_version": understanding.prompt_version,
            }
        document.doc_metadata = doc_meta or None
        document.status = DocumentStatus.READY
        document.processed_at = datetime.now(timezone.utc)
        db.commit()

        # 3.1 map read. Runs after ready on purpose: the source is already searchable,
        # so a failure here costs suggestions, never the upload.
        _read_for_map(db, document)

        if flagged:
            # Flagged is not blocked: a vendor PDF may legitimately contain the word
            # "ignore". It is surfaced so a human can look.
            logger.warning(
                "document %s ready with %s chunk(s) containing instruction-like text",
                document.id,
                flagged,
            )
        logger.info("document %s ready with %s chunks", document.id, stored)
    except Exception as exc:
        db.rollback()
        logger.exception("ingestion failed for %s", document_id)
        document = db.get(Document, document_id)
        if document is not None:
            document.status = DocumentStatus.FAILED
            raw = str(exc)[:2000]
            document.error_message = (
                raw if type(exc).__name__ == "ExtractionError" else f"{type(exc).__name__}: {exc}"[:2000]
            )
            db.commit()
        raise
    finally:
        db.close()


def _read_for_map(db: Session, document: Document) -> None:
    """Propose products and relationships from a source that is already ready."""
    if not settings.graph_extraction_enabled or document.org_id is None:
        return
    try:
        from app.catalog.graph_ingest import GraphIngestor

        summary = GraphIngestor(db).ingest_document(document)
        if summary.total_suggestions or summary.products_created:
            extra = dict(document.doc_metadata or {})
            extra["map_read"] = summary.as_dict()
            document.doc_metadata = extra
            db.commit()
    except Exception:  # noqa: BLE001 - suggestions are never worth failing an upload
        db.rollback()
        logger.warning("map read failed for document %s", document.id, exc_info=True)


def set_approval_state(db: Session, document: Document, state: str) -> Document:
    """Promotion gate: incomplete metadata cannot become `approved` unless auto-approve is on."""
    if (
        state == ApprovalState.APPROVED
        and not document.metadata_complete
        and not settings.auto_approve_uploads
    ):
        raise AppError(
            "cannot approve a document with incomplete metadata; missing: "
            + ", ".join(document.metadata_missing or [])
        )
    document.approval_state = state
    db.commit()
    db.refresh(document)
    return document


def delete_document(db: Session, document: Document) -> None:
    with suppress(Exception):
        get_storage().delete(document.storage_key)
    db.delete(document)
    db.commit()
