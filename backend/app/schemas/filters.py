from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class FilterSearchConfig(BaseModel):
    instructions: str
    outputMode: str  # "warrants" | "answers" | "relevance"


class FilterDefinition(BaseModel):
    name: str
    statement: str
    description: Optional[str] = None
    search: FilterSearchConfig


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
    created_at: datetime
    updated_at: datetime
    archived_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
