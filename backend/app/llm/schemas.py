"""Pydantic response models for structured LLM outputs."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StreamedFilter(StrictModel):
    id: str
    name: str
    description: str
    mode: Literal["claim", "question", "topic"]


class OnboardingFiltersResponse(StrictModel):
    proposedFilters: list[StreamedFilter]


class DocumentSummaryResponse(StrictModel):
    summary: str


class FilterSearchMatch(StrictModel):
    itemId: str
    sourceType: str
    sourceId: str
    result: str


class FilterSearchResponse(StrictModel):
    matches: list[FilterSearchMatch]


class SearchSummaryCitation(StrictModel):
    paperMatchId: str
    itemId: str
    sourceType: str
    sourceId: str
    citedFor: str


class SearchSummaryResponse(StrictModel):
    summary: str
    citations: list[SearchSummaryCitation]


class IdeaMapCitation(StrictModel):
    startBlockId: str
    endBlockId: str
    sectionTitle: str


class IdeaMapCoreClaim(StrictModel):
    id: str
    text: str


class IdeaMapClaimsResponse(StrictModel):
    claims: list[IdeaMapCoreClaim]


class IdeaMapWarrant(StrictModel):
    id: str
    text: str
    citation: IdeaMapCitation


class IdeaMapWarrantsResponse(StrictModel):
    warrants: list[IdeaMapWarrant]


class IdeaMapClaim(StrictModel):
    id: str
    text: str
    warrants: list[IdeaMapWarrant]


class IdeaMapResponse(StrictModel):
    claims: list[IdeaMapClaim]
