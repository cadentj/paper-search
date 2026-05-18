import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, Text, UniqueConstraint

from paper_search_core.models.base import Base


class Paper(Base):
    __tablename__ = "papers"
    __table_args__ = (
        UniqueConstraint("source_type", "source_id", name="uq_papers_source"),
    )

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    source_type = Column(Text, nullable=False, default="arxiv")
    source_id = Column(Text, nullable=True)

    title = Column(Text, nullable=False)
    abstract = Column(Text, nullable=False)
    search_text = Column(Text, nullable=False, default="")
    authors = Column(JSON, nullable=False, default=list)
    categories = Column(JSON, nullable=True)
    published_at = Column(DateTime, nullable=True)
    html_url = Column(Text, nullable=True)
    source_url = Column(Text, nullable=True)

    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
