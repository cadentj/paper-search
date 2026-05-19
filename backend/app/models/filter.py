import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import Column, DateTime, ForeignKey, JSON, Text

from app.models.base import Base


class FilterPayload(BaseModel):
    id: str
    name: str
    definition: dict


class Filter(BaseModel):
    id: str
    name: str
    definition: dict
    status: str
    source: str = "manual"
    parent_filter_id: Optional[str] = None
    proposed_action: Optional[str] = None
    target_filter_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    archived_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SQLAFilter(Base):
    __tablename__ = "filters"

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(Text, nullable=False)
    definition = Column(JSON, nullable=False)
    status = Column(Text, nullable=False, default="active")
    source = Column(Text, nullable=False, default="manual")
    parent_filter_id = Column(Text, ForeignKey("filters.id"), nullable=True)
    proposed_action = Column(Text, nullable=True)  # "create", "revise", "delete"
    target_filter_id = Column(Text, ForeignKey("filters.id"), nullable=True)

    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    archived_at = Column(DateTime, nullable=True)

    def to_pydantic(self) -> Filter:
        return Filter.model_validate(self)

    def to_search_payload(self) -> FilterPayload:
        return FilterPayload(
            id=self.id,
            name=self.name,
            definition=dict(self.definition or {}),
        )
