from datetime import date, datetime, timezone

from sqlalchemy import Column, Date, DateTime, ForeignKey, Index, Integer, Text

from app.models.base import Base


class SourceDailyRollup(Base):
    __tablename__ = "source_daily_rollups"

    source_type = Column(Text, primary_key=True)
    run_date = Column(Date, primary_key=True)
    total_count = Column(Integer, nullable=False, default=0)
    searchable_count = Column(Integer, nullable=False, default=0)
    synced_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class SourceDailyCandidate(Base):
    __tablename__ = "source_daily_candidates"
    __table_args__ = (
        Index("ix_source_daily_candidates_source_date", "source_type", "run_date"),
    )

    source_type = Column(Text, primary_key=True)
    run_date = Column(Date, primary_key=True)
    source_id = Column(Text, primary_key=True)
    paper_id = Column(Text, ForeignKey("papers.id"), nullable=False)
