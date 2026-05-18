import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, Text, UniqueConstraint

from paper_search_core.models.base import Base
from paper_search_core.schemas.daily_search import PaperPayload, paper_item_id


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

    def to_search_payload(self) -> PaperPayload:
        source_type = self.source_type or "arxiv"
        source_id = self.source_id or ""
        return PaperPayload(
            id=self.id,
            title=self.title,
            source_type=source_type,
            source_id=source_id,
            item_id=paper_item_id(source_type, source_id),
            text=self.search_text or self.abstract,
            authors=list(self.authors or []),
        )
