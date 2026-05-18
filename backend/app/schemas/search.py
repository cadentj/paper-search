from pydantic import BaseModel, Field
from datetime import datetime, date
from typing import Optional


class SearchRunResponse(BaseModel):
    id: str
    status: str
    run_date: date
    candidate_count: Optional[int] = None
    candidate_counts: dict | None = None
    match_count: Optional[int] = None
    summary: Optional[str] = None
    summary_citations: list
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CreateDailySearchRequest(BaseModel):
    run_date: date | None = None


class AvailableSearchDate(BaseModel):
    date: date
    count: int
    total_count: int | None = None
    counts_by_source: dict = Field(default_factory=dict)


class AvailableSearchDatesResponse(BaseModel):
    default_date: date | None
    dates: list[AvailableSearchDate]


class PaperMatchResponse(BaseModel):
    id: str
    search_run_id: str
    filter_id: str
    paper_id: str
    stance: str
    relevance_score: float
    confidence: Optional[float] = None
    rationale: str
    matched_claims: list
    abstract_evidence: list
    llm_model: Optional[str] = None
    created_at: datetime

    # Joined fields
    paper_title: Optional[str] = None
    paper_authors: Optional[list] = None
    paper_arxiv_id: Optional[str] = None
    paper_source_type: Optional[str] = None
    paper_source_id: Optional[str] = None
    paper_source_url: Optional[str] = None
    paper_item_label: Optional[str] = None
    paper_abstract: Optional[str] = None
    filter_name: Optional[str] = None

    model_config = {"from_attributes": True}
