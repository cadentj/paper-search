import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Text, DateTime, JSON

from app.models.base import Base


class ResearchProfileImport(Base):
    __tablename__ = "research_profile_imports"

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    status = Column(Text, nullable=False, default="pending")
    source_type = Column(Text, nullable=False, default="semantic_scholar")
    source_url = Column(Text, nullable=False)
    external_author_id = Column(Text, nullable=True)
    display_name = Column(Text, nullable=True)
    affiliation = Column(Text, nullable=True)
    paper_count = Column(Text, nullable=True)
    publications = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)

    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
