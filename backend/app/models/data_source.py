import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, JSON, Text

from app.models.base import Base
from app.schemas.data_sources import DataSourceResponse


class DataSource(Base):
    __tablename__ = "data_sources"

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    source_type = Column(Text, unique=True, nullable=False)
    name = Column(Text, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    settings = Column(JSON, nullable=False, default=dict)

    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def to_pydantic(self) -> DataSourceResponse:
        return DataSourceResponse.model_validate(self)
