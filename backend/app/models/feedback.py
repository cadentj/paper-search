import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Text, DateTime

from app.models.base import Base


class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    target_type = Column(Text, nullable=False)
    target_id = Column(Text, nullable=False)

    value = Column(Text, nullable=False)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
