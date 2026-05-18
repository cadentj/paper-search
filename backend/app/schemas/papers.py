from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class PaperResponse(BaseModel):
    id: str
    arxiv_id: Optional[str] = None
    source_type: str = "arxiv"
    source_id: Optional[str] = None
    title: str
    abstract: str
    authors: list
    categories: Optional[list] = None
    published_at: Optional[datetime] = None
    html_url: Optional[str] = None
    landing_url: Optional[str] = None
    source_url: Optional[str] = None
    source_metadata: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class IdeaMapResponse(BaseModel):
    id: str
    job_id: Optional[str] = None
    paper_id: str
    status: str
    claims: list
    source_url: Optional[str] = None
    dropped_reason: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
