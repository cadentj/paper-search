import uuid
from datetime import datetime, date, timezone

from sqlalchemy import Column, Text, DateTime, Date, Integer, JSON

from app.models.base import Base


class SearchRun(Base):
    __tablename__ = "search_runs"

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    status = Column(Text, nullable=False, default="queued")
    run_date = Column(Date, nullable=False, default=lambda: date.today())

    candidate_count = Column(Integer, nullable=True)
    match_count = Column(Integer, nullable=True)
    summary = Column(Text, nullable=True)
    summary_citations = Column(JSON, nullable=False, default=list)
    stage = Column(Text, nullable=False, default="queued")
    progress_current = Column(Integer, nullable=False, default=0)
    progress_total = Column(Integer, nullable=False, default=1)
    progress_message = Column(Text, nullable=False, default="Queued")
    progress_log = Column(JSON, nullable=False, default=list)

    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
