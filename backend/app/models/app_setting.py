from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, JSON, Text

from app.models.base import Base


class SQLAAppSetting(Base):
    __tablename__ = "app_settings"

    key = Column(Text, primary_key=True)
    value = Column(JSON, nullable=False)
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
