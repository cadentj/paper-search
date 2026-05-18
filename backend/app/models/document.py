import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, Text

from app.models.base import Base


class Document(Base):
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

    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
