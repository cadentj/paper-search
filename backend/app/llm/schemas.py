"""Pydantic response models for structured LLM outputs."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StreamedFilter(StrictModel):
    id: str
    name: str
    description: str
    mode: Literal["claim", "topic"]


class OnboardingFiltersResponse(StrictModel):
    proposedFilters: list[StreamedFilter]


class DocumentSummaryResponse(StrictModel):
    summary: str


class ClaimFilterResult(StrictModel):
    verdict: Literal["positive", "negative"]
    reason: str
    evidence: str | None = None


class TopicFilterResult(StrictModel):
    reason: str
    evidence: str | None = None


class ClaimFilterSearchMatch(StrictModel):
    itemId: str
    sourceType: str
    sourceId: str
    verdict: Literal["positive", "negative"]
    reason: str
    evidence: str | None = None


class TopicFilterSearchMatch(StrictModel):
    itemId: str
    sourceType: str
    sourceId: str
    reason: str
    evidence: str | None = None


class ClaimFilterSearchResponse(StrictModel):
    matches: list[ClaimFilterSearchMatch]


class TopicFilterSearchResponse(StrictModel):
    matches: list[TopicFilterSearchMatch]


class CreateFeedbackAction(StrictModel):
    action: Literal["create"]
    name: str
    description: str
    mode: Literal["claim", "topic"]
    rationale: str = ""


class ReviseFeedbackAction(StrictModel):
    action: Literal["revise"]
    name: str
    description: str
    mode: Literal["claim", "topic"]
    target_filter_id: str
    rationale: str = ""


class DeleteFeedbackAction(StrictModel):
    action: Literal["delete"]
    target_filter_id: str
    rationale: str = ""


FeedbackAction = Annotated[
    CreateFeedbackAction | ReviseFeedbackAction | DeleteFeedbackAction,
    Field(discriminator="action"),
]


class FeedbackReflectionResponse(StrictModel):
    actions: list[FeedbackAction]


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
