import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Text, DateTime, ForeignKey

from app.models.base import Base


class PaperNote(Base):
    __tablename__ = "paper_notes"

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    paper_id = Column(Text, ForeignKey("papers.id"), nullable=False, unique=True)
    text = Column(Text, nullable=False, default="")

    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
