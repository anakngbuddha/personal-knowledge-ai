import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import (
    AppError,
    DuplicateDocument,
    MalwareDetected,
    ScannerUnavailable,
    SsrfBlocked,
    StorageError,
    UnsafeFile,
    UnsupportedFileType,
)
from app.core.logging import get_logger
from app.db.models import Document, DocumentChunk, DocumentStatus, IngestionJob
from app.db.session import get_db
from app.documents import service
from app.documents.metadata import DocumentMetadataIn
from app.documents.schemas import (
    ApprovalIn,
    BulkUploadOut,
    ChunkOut,
    DocumentOut,
    DocumentStatusOut,
    MetadataPatchIn,
    PasteIngestIn,
    UploadReport,
    UrlIngestIn,
)
from app.security.deps import resolve_principal
from app.security.labels import ApprovalState, SourceType, normalize
from app.security.principal import Principal

logger = get_logger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])


def _scoped(db: Session, principal: Principal, document_id: uuid.UUID) -> Document:
    """Fetch within the caller's tenant. A miss is 404, never 403: another tenant's
    document must not be distinguishable from one that does not exist."""
    document = db.scalars(
        select(Document).where(Document.id == document_id, Document.org_id == principal.org_id)
    ).first()
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")
    return document


def _as_http(exc: Exception) -> HTTPException:
    if isinstance(exc, UnsupportedFileType):
        return HTTPException(status_code=415, detail=str(exc))
    if isinstance(exc, (MalwareDetected, UnsafeFile)):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, ScannerUnavailable):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, SsrfBlocked):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, StorageError):
        return HTTPException(status_code=502, detail=str(exc))
    if isinstance(exc, AppError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


def _metadata_from_form(
    *,
    title: str | None,
    vendor: str | None,
    ownership: str,
    products_referenced: str | None,
    account_ref: str | None,
    approval_state: str,
    sensitivity: str,
    valid_until: str | None,
    source_of_truth_url: str | None,
    source_type: str = str(SourceType.UPLOAD),
) -> DocumentMetadataIn:
    try:
        return DocumentMetadataIn(
            title=title,
            vendor=vendor,
            ownership=ownership,
            products_referenced=products_referenced or [],
            account_ref=account_ref,
            approval_state=approval_state,
            sensitivity=sensitivity,
            valid_until=valid_until or None,
            source_of_truth_url=source_of_truth_url,
            source_type=source_type,
        )
    except Exception as exc:  # noqa: BLE001 - pydantic validation detail is useful here
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("", response_model=BulkUploadOut, status_code=status.HTTP_202_ACCEPTED)
async def upload_documents(
    files: list[UploadFile] = File(...),
    title: str | None = Form(default=None),
    vendor: str | None = Form(default=None),
    ownership: str = Form(default="unknown"),
    products_referenced: str | None = Form(default=None),
    account_ref: str | None = Form(default=None),
    approval_state: str = Form(default="draft"),
    sensitivity: str = Form(default="internal"),
    valid_until: str | None = Form(default=None),
    source_of_truth_url: str | None = Form(default=None),
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> BulkUploadOut:
    """Bulk upload. Many files at once, or a whole folder drop from the browser.

    One bad file never fails the batch: each file gets its own result row. That is the
    difference between a folder drop that works and one that has to be retried by hand.
    Metadata supplied here applies to every file in the batch, which is the common case
    for a folder of one vendor's collateral.
    """
    if not files:
        raise HTTPException(status_code=400, detail="no files supplied")
    if len(files) > 200:
        raise HTTPException(status_code=413, detail="upload at most 200 files per request")

    # `title` only makes sense for a single file; for a batch the filename wins.
    shared = _metadata_from_form(
        title=title if len(files) == 1 else None,
        vendor=vendor,
        ownership=ownership,
        products_referenced=products_referenced,
        account_ref=account_ref,
        approval_state=approval_state,
        sensitivity=sensitivity,
        valid_until=valid_until,
        source_of_truth_url=source_of_truth_url,
    )

    results: list[UploadReport] = []
    for upload in files:
        name = upload.filename or "upload"
        try:
            data = await upload.read()
            if not data:
                raise AppError("file is empty")
            if len(data) > settings.max_upload_bytes:
                raise AppError(f"file exceeds the {settings.max_upload_mb} MB limit")
            document = service.create_document(
                db,
                principal=principal,
                original_filename=name,
                data=data,
                mime_type=upload.content_type,
                metadata=shared,
            )
            service.enqueue_ingestion(db, document)
            results.append(
                UploadReport(
                    original_filename=name,
                    status="queued",
                    document_id=document.id,
                    detail=(
                        "metadata incomplete: " + ", ".join(document.metadata_missing)
                        if document.metadata_missing
                        else None
                    ),
                )
            )
        except DuplicateDocument as exc:
            db.rollback()
            results.append(
                UploadReport(
                    original_filename=name,
                    status="duplicate",
                    duplicate_of=exc.existing_id,
                    detail=str(exc),
                )
            )
        except Exception as exc:  # noqa: BLE001 - per-file isolation is the point
            db.rollback()
            logger.warning("upload rejected for %r: %s", name, exc)
            results.append(
                UploadReport(
                    original_filename=name,
                    status="rejected",
                    detail=f"{type(exc).__name__}: {exc}",
                )
            )
        finally:
            await upload.close()

    return BulkUploadOut(
        queued=sum(r.status == "queued" for r in results),
        duplicates=sum(r.status == "duplicate" for r in results),
        rejected=sum(r.status == "rejected" for r in results),
        results=results,
    )


@router.post("/url", response_model=DocumentOut, status_code=status.HTTP_202_ACCEPTED)
def ingest_url(
    payload: UrlIngestIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> Document:
    """Ingest a URL through the SSRF-safe fetcher."""
    from app.net import ssrf

    try:
        resource = ssrf.fetch(payload.url)
        meta = DocumentMetadataIn(
            title=payload.title,
            vendor=payload.vendor,
            ownership=payload.ownership,
            products_referenced=payload.products_referenced,
            account_ref=payload.account_ref,
            approval_state=payload.approval_state,
            sensitivity=payload.sensitivity,
            valid_until=payload.valid_until,
            source_type=str(SourceType.URL),
            source_url=resource.final_url,
            # For a resold vendor page, the fetched URL *is* the upstream source of
            # truth unless the caller named a different one. Phase 9 re-checks it.
            source_of_truth_url=payload.source_of_truth_url or resource.final_url,
        )
        document = service.create_document(
            db,
            principal=principal,
            original_filename=_filename_for_url(resource.final_url, resource.content_type),
            data=resource.data,
            mime_type=resource.content_type,
            metadata=meta,
        )
        service.enqueue_ingestion(db, document)
        return document
    except DuplicateDocument as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise _as_http(exc) from exc


def _filename_for_url(url: str, content_type: str | None) -> str:
    from urllib.parse import urlparse

    path = urlparse(url).path
    name = path.rstrip("/").split("/")[-1] or urlparse(url).netloc
    if "." in name:
        return name
    suffix = {
        "application/pdf": ".pdf",
        "text/plain": ".txt",
        "text/markdown": ".md",
    }.get((content_type or "").lower(), ".html")
    return f"{name}{suffix}"


@router.post("/paste", response_model=DocumentOut, status_code=status.HTTP_202_ACCEPTED)
def ingest_paste(
    payload: PasteIngestIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> Document:
    """Pasted text: discovery notes, an RFP extract, call notes typed up after the fact.

    This is the only discovery input path, by decision: audio and video ingestion are
    out of scope in Project_Plan.md section 0.
    """
    try:
        meta = DocumentMetadataIn(
            title=payload.title,
            vendor=payload.vendor,
            ownership=payload.ownership,
            products_referenced=payload.products_referenced,
            account_ref=payload.account_ref,
            approval_state=payload.approval_state,
            sensitivity=payload.sensitivity,
            valid_until=payload.valid_until,
            source_type=str(SourceType.PASTE),
            source_of_truth_url=payload.source_of_truth_url,
        )
        safe_title = "".join(ch for ch in payload.title if ch.isalnum() or ch in " -_").strip()
        document = service.create_document(
            db,
            principal=principal,
            original_filename=f"{safe_title or 'pasted-note'}.md",
            data=payload.text.encode("utf-8"),
            mime_type="text/markdown",
            metadata=meta,
        )
        service.enqueue_ingestion(db, document)
        return document
    except DuplicateDocument as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise _as_http(exc) from exc


@router.get("", response_model=list[DocumentOut])
def list_documents(
    limit: int = 50,
    offset: int = 0,
    status_filter: str | None = None,
    metadata_complete: bool | None = None,
    include_superseded: bool = False,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> list[Document]:
    statement = select(Document).where(Document.org_id == principal.org_id)
    if not include_superseded:
        statement = statement.where(Document.is_current.is_(True))
    if status_filter:
        statement = statement.where(Document.status == status_filter)
    if metadata_complete is not None:
        statement = statement.where(Document.metadata_complete.is_(metadata_complete))
    statement = (
        statement.order_by(Document.uploaded_at.desc())
        .limit(min(max(limit, 1), 200))
        .offset(max(offset, 0))
    )
    return list(db.scalars(statement))


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> Document:
    return _scoped(db, principal, document_id)


@router.patch("/{document_id}", response_model=DocumentOut)
def patch_metadata(
    document_id: uuid.UUID,
    payload: MetadataPatchIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> Document:
    """Fill in the curation metadata that bulk upload deliberately left blank.

    This is also where a person corrects the 2.2 understand step: the summary and the
    auto-filled vendor, products, and validity date are all editable here, and a human
    edit is never overwritten by a later re-read.
    """
    document = _scoped(db, principal, document_id)
    merged = DocumentMetadataIn(
        title=payload.title if payload.title is not None else document.title,
        vendor=payload.vendor if payload.vendor is not None else document.vendor,
        ownership=payload.ownership or document.ownership,
        products_referenced=(
            payload.products_referenced
            if payload.products_referenced is not None
            else (document.products_referenced or [])
        ),
        account_ref=payload.account_ref if payload.account_ref is not None else document.account_ref,
        approval_state=payload.approval_state or document.approval_state,
        sensitivity=payload.sensitivity or document.sensitivity,
        valid_until=payload.valid_until or document.valid_until,
        source_type=document.source_type,
        source_url=document.source_url,
        source_of_truth_url=(
            payload.source_of_truth_url
            if payload.source_of_truth_url is not None
            else document.source_of_truth_url
        ),
    )
    error = merged.promotion_error()
    if error:
        raise HTTPException(status_code=400, detail=error)

    missing = merged.missing_fields()
    document.title = merged.title
    document.vendor = merged.vendor
    document.ownership = merged.ownership
    document.products_referenced = merged.products_referenced or None
    document.account_ref = merged.account_ref
    document.approval_state = merged.approval_state
    document.sensitivity = merged.sensitivity
    document.valid_until = merged.valid_until
    document.source_of_truth_url = merged.source_of_truth_url
    document.metadata_complete = not missing
    document.metadata_missing = missing or None
    if payload.summary is not None:
        document.summary = payload.summary.strip() or None
        document.understanding_source = "person"
    db.commit()
    db.refresh(document)
    return document


@router.post("/{document_id}/approval", response_model=DocumentOut)
def set_approval(
    document_id: uuid.UUID,
    payload: ApprovalIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> Document:
    document = _scoped(db, principal, document_id)
    try:
        state = normalize(payload.approval_state, ApprovalState)
        return service.set_approval_state(db, document, state)
    except (ValueError, AppError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> None:
    service.delete_document(db, _scoped(db, principal, document_id))


@router.post("/{document_id}/process", response_model=DocumentStatusOut)
def reprocess_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> DocumentStatusOut:
    document = _scoped(db, principal, document_id)
    if document.status == DocumentStatus.PROCESSING:
        raise HTTPException(status_code=409, detail="document is already processing")
    job = service.queue.enqueue(db, document_id=document.id, org_id=document.org_id)

    return DocumentStatusOut(
        id=document.id,
        status=document.status,
        chunk_count=document.chunk_count,
        error_message=document.error_message,
        job_status=job.status,
        attempts=job.attempts,
    )


@router.get("/{document_id}/status", response_model=DocumentStatusOut)
def document_status(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> DocumentStatusOut:
    document = _scoped(db, principal, document_id)
    job = db.scalars(
        select(IngestionJob)
        .where(IngestionJob.document_id == document.id)
        .order_by(IngestionJob.created_at.desc())
        .limit(1)
    ).first()
    return DocumentStatusOut(
        id=document.id,
        status=document.status,
        chunk_count=document.chunk_count,
        error_message=document.error_message,
        job_status=job.status if job else None,
        attempts=job.attempts if job else None,
    )


@router.get("/{document_id}/chunks", response_model=list[ChunkOut])
def document_chunks(
    document_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> list[ChunkOut]:
    """Inspection endpoint: chunk metadata and citation anchors must survive ingestion."""
    _scoped(db, principal, document_id)
    rows = db.scalars(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
        .limit(min(limit, 200))
        .offset(offset)
    )
    return [
        ChunkOut(
            id=row.id,
            chunk_index=row.chunk_index,
            page_number=row.page_number,
            slide_number=row.slide_number,
            sheet_name=row.sheet_name,
            cell_range=row.cell_range,
            section_title=row.section_title,
            heading_path=row.heading_path,
            citation=(row.chunk_metadata or {}).get("citation"),
            start_offset=row.start_offset,
            end_offset=row.end_offset,
            text=row.text,
            has_embedding=row.embedding is not None,
            injection_flags=row.injection_flags,
            is_table=bool((row.chunk_metadata or {}).get("is_table")),
            has_parent_passage=bool((row.chunk_metadata or {}).get("parent_text")),
        )
        for row in rows
    ]
