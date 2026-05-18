from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Text

from app.models.base import Base


class SearchRunPaper(Base):
    __tablename__ = "search_run_papers"

    search_run_id = Column(Text, ForeignKey("search_runs.id"), primary_key=True)
    paper_id = Column(Text, ForeignKey("papers.id"), primary_key=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
