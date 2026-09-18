import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import StorageError, UnsupportedFileType
from app.db.models import Document, DocumentChunk, DocumentStatus
from app.db.session import get_db
from app.documents import service
from app.documents.schemas import ChunkOut, DocumentOut, DocumentStatusOut

router = APIRouter(prefix="/documents", tags=["documents"])


def _get_document(db: Session, document_id: uuid.UUID) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")
    return document


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile,
    db: Session = Depends(get_db),
) -> Document:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="uploaded file is empty")
    limit = settings.max_upload_mb * 1024 * 1024
    if len(data) > limit:
        raise HTTPException(
            status_code=413, detail=f"file exceeds the {settings.max_upload_mb} MB limit"
        )

    try:
        document = service.create_document(
            db,
            original_filename=file.filename or "upload",
            data=data,
            mime_type=file.content_type,
        )
    except UnsupportedFileType as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except StorageError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    background_tasks.add_task(service.process_document, document.id)
    return document


@router.get("", response_model=list[DocumentOut])
def list_documents(db: Session = Depends(get_db)) -> list[Document]:
    return list(db.scalars(select(Document).order_by(Document.uploaded_at.desc())))


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: uuid.UUID, db: Session = Depends(get_db)) -> Document:
    return _get_document(db, document_id)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: uuid.UUID, db: Session = Depends(get_db)) -> None:
    service.delete_document(db, _get_document(db, document_id))


@router.post("/{document_id}/process", response_model=DocumentStatusOut)
def process_document(
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> DocumentStatusOut:
    document = _get_document(db, document_id)
    if document.status == DocumentStatus.PROCESSING:
        raise HTTPException(status_code=409, detail="document is already processing")
    background_tasks.add_task(service.process_document, document.id)
    return DocumentStatusOut(
        id=document.id,
        status=DocumentStatus.PROCESSING,
        chunk_count=document.chunk_count,
        error_message=None,
    )


@router.get("/{document_id}/status", response_model=DocumentStatusOut)
def document_status(document_id: uuid.UUID, db: Session = Depends(get_db)) -> DocumentStatusOut:
    document = _get_document(db, document_id)
    return DocumentStatusOut(
        id=document.id,
        status=document.status,
        chunk_count=document.chunk_count,
        error_message=document.error_message,
    )


@router.get("/{document_id}/chunks", response_model=list[ChunkOut])
def document_chunks(
    document_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> list[ChunkOut]:
    """Inspection endpoint for the Phase 1 exit criteria: chunk metadata must survive ingestion."""
    _get_document(db, document_id)
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
            section_title=row.section_title,
            start_offset=row.start_offset,
            end_offset=row.end_offset,
            text=row.text,
            has_embedding=row.embedding is not None,
        )
        for row in rows
    ]
