import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Index, JSON, Text
from sqlalchemy.dialects.postgresql import JSONB

from app.models.base import Base
from app.schemas.jobs import JobResponse


ProgressJSON = JSON().with_variant(JSONB, "postgresql")


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_subject", "subject_type", "subject_id"),
    )

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    kind = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="queued")
    subject_type = Column(Text, nullable=True)
    subject_id = Column(Text, nullable=True)
    queue_name = Column(Text, nullable=True)
    queue_job_id = Column(Text, nullable=True)
    progress = Column(ProgressJSON, nullable=False, default=dict)
    error = Column(Text, nullable=True)

    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def to_pydantic(self) -> JobResponse:
        return JobResponse.model_validate(self)
