import uuid
from datetime import date, datetime, timezone
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import Column, Date, DateTime, Integer, JSON, Text

from app.models.base import Base


class SearchRun(BaseModel):
    id: str
    job_id: Optional[str] = None
    summary_job_id: Optional[str] = None
    status: str
    run_date: date
    candidate_count: Optional[int] = None
    candidate_counts: dict | None = None
    match_count: Optional[int] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SQLASearchRun(Base):
    __tablename__ = "search_runs"

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    status = Column(Text, nullable=False, default="queued")
    run_date = Column(Date, nullable=False, default=lambda: date.today())

    candidate_count = Column(Integer, nullable=True)
    candidate_counts = Column(JSON, nullable=True)
    match_count = Column(Integer, nullable=True)
    summary = Column(Text, nullable=True)
    summary_citations = Column(JSON, nullable=False, default=list)

    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    def to_pydantic(
        self,
        job_id: str | None = None,
        summary_job_id: str | None = None,
    ) -> SearchRun:
        resp = SearchRun.model_validate(self)
        updates: dict[str, str] = {}
        if job_id is not None:
            updates["job_id"] = job_id
        if summary_job_id is not None:
            updates["summary_job_id"] = summary_job_id
        if updates:
            return resp.model_copy(update=updates)
        return resp
