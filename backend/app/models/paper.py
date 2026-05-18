import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Text, DateTime, JSON

from app.models.base import Base


class Paper(Base):
    __tablename__ = "papers"

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    arxiv_id = Column(Text, unique=True, nullable=True)

    title = Column(Text, nullable=False)
    abstract = Column(Text, nullable=False)
    authors = Column(JSON, nullable=False, default=list)
    categories = Column(JSON, nullable=True)
    published_at = Column(DateTime, nullable=True)
    html_url = Column(Text, nullable=True)
    landing_url = Column(Text, nullable=True)

    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
