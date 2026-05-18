import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Text, DateTime, JSON, ForeignKey

from app.models.base import Base


class IdeaMap(Base):
    __tablename__ = "idea_maps"

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    paper_id = Column(Text, ForeignKey("papers.id"), nullable=False)
    status = Column(Text, nullable=False, default="queued")

    claims = Column(JSON, nullable=False, default=list)
    source_url = Column(Text, nullable=True)
    dropped_reason = Column(Text, nullable=True)
    llm_model = Column(Text, nullable=True)
    llm_response_id = Column(Text, nullable=True)
    error = Column(Text, nullable=True)

    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
