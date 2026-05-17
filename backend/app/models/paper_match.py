import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Text, DateTime, Float, JSON, ForeignKey

from app.models.base import Base


class PaperMatch(Base):
    __tablename__ = "paper_matches"

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    search_run_id = Column(Text, ForeignKey("search_runs.id"), nullable=False)
    filter_id = Column(Text, ForeignKey("filters.id"), nullable=False)
    paper_id = Column(Text, ForeignKey("papers.id"), nullable=False)

    stance = Column(Text, nullable=False)
    relevance_score = Column(Float, nullable=False)
    confidence = Column(Float, nullable=True)

    rationale = Column(Text, nullable=False)
    matched_claims = Column(JSON, nullable=False, default=list)
    abstract_evidence = Column(JSON, nullable=False, default=list)

    llm_model = Column(Text, nullable=True)
    llm_response_id = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
