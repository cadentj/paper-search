from datetime import datetime, timezone

from sqlalchemy import Column, Text, DateTime, ForeignKey

from app.models.base import Base


class PaperHtml(Base):
    __tablename__ = "paper_html"

    paper_id = Column(Text, ForeignKey("papers.id"), primary_key=True)
    source_url = Column(Text, nullable=False)
    html = Column(Text, nullable=False)
    content_hash = Column(Text, nullable=True)
    fetched_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
