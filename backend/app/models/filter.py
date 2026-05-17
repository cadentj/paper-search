import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Text, DateTime, JSON

from app.models.base import Base


class Filter(Base):
    __tablename__ = "filters"

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(Text, nullable=False)
    definition = Column(JSON, nullable=False)
    status = Column(Text, nullable=False, default="active")

    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    archived_at = Column(DateTime, nullable=True)
