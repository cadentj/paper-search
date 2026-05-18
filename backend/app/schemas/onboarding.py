from pydantic import BaseModel
from datetime import datetime
from typing import Literal, Optional


class OnboardingStatusResponse(BaseModel):
    completed: bool
    active_filter_count: int


class OnboardingExtractionCreate(BaseModel):
    input_text: str


class ProposedFilter(BaseModel):
    id: str
    name: str
    description: str
    mode: Literal["claim", "topic"] = "topic"


class OnboardingExtractionResponse(BaseModel):
    id: str
    job_id: Optional[str] = None
    status: str
    input_text: str
    proposed_filters: list[ProposedFilter | dict]
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class OnboardingCompleteRequest(BaseModel):
    filters: list[dict]


class OnboardingGenerationCreate(BaseModel):
    input_text: str
    document_ids: list[str] = []


class DraftFilterPromoteRequest(BaseModel):
    filter_ids: list[str]
