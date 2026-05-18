from datetime import datetime

from pydantic import BaseModel


class DocumentResponse(BaseModel):
    id: str
    original_filename: str
    content_type: str
    size_bytes: int
    page_count: int
    storage_path: str
    extracted_text_path: str | None = None
    summary: str | None = None
    status: str
    error: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentUploadResponse(DocumentResponse):
    job_id: str
