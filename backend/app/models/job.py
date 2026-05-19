import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field
from sqlalchemy import Column, DateTime, Index, JSON, Text
from sqlalchemy.dialects.postgresql import JSONB

from app.models.base import Base


ProgressJSON = JSON().with_variant(JSONB, "postgresql")


class Job(BaseModel):
    id: str
    kind: str
    status: str
    subject_type: str | None = None
    subject_id: str | None = None
    queue_name: str | None = None
    progress: dict = Field(default_factory=dict)
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SQLAJob(Base):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_subject", "subject_type", "subject_id"),)

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    kind = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="queued")
    subject_type = Column(Text, nullable=True)
    subject_id = Column(Text, nullable=True)
    queue_name = Column(Text, nullable=True)
    progress = Column(ProgressJSON, nullable=False, default=dict)
    error = Column(Text, nullable=True)

    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    def to_pydantic(self) -> Job:
        return Job.model_validate(self)
