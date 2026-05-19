from pydantic import BaseModel
from datetime import datetime
from typing import Literal, Optional


class FilterDefinition(BaseModel):
    name: str
    description: str
    mode: Literal["claim", "topic"] = "topic"


class FilterCreate(BaseModel):
    name: str
    definition: FilterDefinition


class FilterUpdate(BaseModel):
    name: Optional[str] = None
    definition: Optional[FilterDefinition] = None


class FilterResponse(BaseModel):
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
