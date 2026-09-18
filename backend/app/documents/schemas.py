import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    original_filename: str
    file_type: str
    file_size: int
    status: str
    page_count: int | None = None
    chunk_count: int = 0
    uploaded_at: datetime | None = None
    processed_at: datetime | None = None
    error_message: str | None = None


class DocumentStatusOut(BaseModel):
    id: uuid.UUID
    status: str
    chunk_count: int
    error_message: str | None = None


class ChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chunk_index: int
    page_number: int | None
    section_title: str | None
    start_offset: int | None
    end_offset: int | None
    text: str
    has_embedding: bool = True
