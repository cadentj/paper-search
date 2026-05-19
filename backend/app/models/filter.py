import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Text, DateTime, ForeignKey, JSON

from app.models.base import Base
from app.schemas.daily_search import FilterPayload
from app.schemas.filters import FilterResponse


class Filter(Base):
    __tablename__ = "filters"

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(Text, nullable=False)
    definition = Column(JSON, nullable=False)
    status = Column(Text, nullable=False, default="active")
    source = Column(Text, nullable=False, default="manual")
    parent_filter_id = Column(Text, ForeignKey("filters.id"), nullable=True)

    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    archived_at = Column(DateTime, nullable=True)

    def to_pydantic(self) -> FilterResponse:
        return FilterResponse.model_validate(self)

    def to_search_payload(self) -> FilterPayload:
        return FilterPayload(
            id=self.id,
            name=self.name,
            definition=dict(self.definition or {}),
        )
