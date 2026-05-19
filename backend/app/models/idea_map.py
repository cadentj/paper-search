import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import Column, DateTime, ForeignKey, JSON, Text

from app.models.base import Base


class IdeaMap(BaseModel):
    id: str
    job_id: Optional[str] = None
    paper_id: str
    status: str
    claims: list
    source_url: Optional[str] = None
    dropped_reason: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SQLAIdeaMap(Base):
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

    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def to_pydantic(self, *, job_id: str | None = None) -> IdeaMap:
        resp = IdeaMap.model_validate(self)
        if job_id is not None:
            return resp.model_copy(update={"job_id": job_id})
        return resp
