import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Text, DateTime, ForeignKey

from app.models.base import Base


class PaperMatch(Base):
    __tablename__ = "paper_matches"

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    search_run_id = Column(Text, ForeignKey("search_runs.id"), nullable=False)
    filter_id = Column(Text, ForeignKey("filters.id"), nullable=False)
    paper_id = Column(Text, ForeignKey("papers.id"), nullable=False)

    result = Column(Text, nullable=False)

    llm_model = Column(Text, nullable=True)
    llm_response_id = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
