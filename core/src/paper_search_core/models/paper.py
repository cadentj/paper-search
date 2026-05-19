import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import JSON, Column, DateTime, Text, UniqueConstraint

from paper_search_core.models.base import Base
from paper_search_core.schemas.daily_search import PaperPayload, paper_item_id


class Paper(BaseModel):
    id: str
    source_type: str = "arxiv"
    source_id: Optional[str] = None
    title: str
    search_text: str
    authors: list
    published_at: Optional[datetime] = None
    html_url: Optional[str] = None
    source_url: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SQLAPaper(Base):
    __tablename__ = "papers"
    __table_args__ = (
        UniqueConstraint("source_type", "source_id", name="uq_papers_source"),
    )

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    source_type = Column(Text, nullable=False, default="arxiv")
    source_id = Column(Text, nullable=True)

    title = Column(Text, nullable=False)
    search_text = Column(Text, nullable=False, default="")
    authors = Column(JSON, nullable=False, default=list)
    published_at = Column(DateTime, nullable=True)
    html_url = Column(Text, nullable=True)
    source_url = Column(Text, nullable=True)

    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def to_pydantic(self) -> Paper:
        return Paper.model_validate(self)

    def to_search_payload(self) -> PaperPayload:
        source_type = self.source_type or "arxiv"
        source_id = self.source_id or ""
        return PaperPayload(
            id=self.id,
            title=self.title,
            source_type=source_type,
            source_id=source_id,
            item_id=paper_item_id(source_type, source_id),
            text=self.search_text,
            authors=list(self.authors or []),
        )
