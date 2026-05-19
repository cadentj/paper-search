from pydantic import BaseModel, Field
from datetime import datetime, date
from typing import Optional


class SearchRunResponse(BaseModel):
    id: str
    job_id: Optional[str] = None
    status: str
    run_date: date
    candidate_count: Optional[int] = None
    candidate_counts: dict | None = None
    match_count: Optional[int] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SummaryCitationResponse(BaseModel):
    paperMatchId: Optional[str] = None
    arxivId: Optional[str] = None
    itemId: Optional[str] = None
    sourceType: Optional[str] = None
    sourceId: Optional[str] = None
    citedFor: str = ""


class DailySearchSummaryResponse(BaseModel):
    search_run_id: str
    summary: str
    citations: list[SummaryCitationResponse] = Field(default_factory=list)


class CreateDailySearchRequest(BaseModel):
    run_date: date | None = None


class DailyCandidateCountResponse(BaseModel):
    date: date
    count: int
    counts_by_source: dict = Field(default_factory=dict)


class PaperMatchResponse(BaseModel):
    id: str
    search_run_id: str
    filter_id: str
    paper_id: str
    result: str
    llm_model: Optional[str] = None
    created_at: datetime

    # Joined fields
    paper_title: Optional[str] = None
    paper_authors: Optional[list] = None
    paper_source_type: Optional[str] = None
    paper_source_id: Optional[str] = None
    paper_source_url: Optional[str] = None
    paper_item_label: Optional[str] = None
    paper_search_text: Optional[str] = None
    filter_name: Optional[str] = None

    model_config = {"from_attributes": True}
