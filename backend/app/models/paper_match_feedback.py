import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Text

from app.models.base import Base


class SQLAPaperMatchFeedback(Base):
    __tablename__ = "paper_match_feedback"

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    paper_match_id = Column(Text, ForeignKey("paper_matches.id"), nullable=True)
    search_run_id = Column(Text, ForeignKey("search_runs.id"), nullable=True)
    filter_id = Column(Text, ForeignKey("filters.id"), nullable=True)
    paper_id = Column(Text, ForeignKey("papers.id"), nullable=False)
    value = Column(Text, nullable=False)  # "up" or "down"
    processed = Column(Boolean, nullable=False, default=False)

    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
