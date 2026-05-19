import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Integer, Text

from app.models.base import Base


class Document(BaseModel):
    id: str
    job_id: Optional[str] = None
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


class SQLADocument(Base):
    __tablename__ = "documents"

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    original_filename = Column(Text, nullable=False)
    content_type = Column(Text, nullable=False)
    size_bytes = Column(Integer, nullable=False)
    page_count = Column(Integer, nullable=False)
    storage_path = Column(Text, nullable=False)
    extracted_text_path = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    status = Column(Text, nullable=False, default="queued")
    error = Column(Text, nullable=True)

    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def to_pydantic(self, *, job_id: str | None = None) -> Document:
        resp = Document.model_validate(self)
        if job_id is not None:
            return resp.model_copy(update={"job_id": job_id})
        return resp
