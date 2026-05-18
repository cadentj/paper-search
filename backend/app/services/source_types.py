"""Shared types for source providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from app.models.paper import Paper


@dataclass(frozen=True)
class CandidateItem:
    source_type: str
    source_id: str
    title: str
    display_text: str
    authors: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    published_at: object | None = None
    html_url: str | None = None
    landing_url: str | None = None
    source_url: str | None = None
    arxiv_id: str | None = None
    metadata: dict = field(default_factory=dict)

    @property
    def item_id(self) -> str:
        return f"{self.source_type}:{self.source_id}"


@dataclass(frozen=True)
class SourceFetchResult:
    items: list[CandidateItem]
    errors: list[str] = field(default_factory=list)
    # Items still in the R2 index but with no excerpt — not sent to the LLM.
    skipped_missing_text: dict[str, int] = field(default_factory=dict)


class SourceProvider(Protocol):
    source_type: str

    def count_for_date(self, run_date: date) -> int:
        ...

    def candidates_for_date(self, run_date: date) -> SourceFetchResult:
        ...

    def html_for_paper(self, paper: Paper) -> dict[str, str | None]:
        ...


def candidate_from_record(record: dict) -> CandidateItem:
    source_type = record.get("source_type") or "arxiv"
    source_id = record.get("source_id") or record.get("arxiv_id") or ""
    return CandidateItem(
        source_type=source_type,
        source_id=source_id,
        title=record.get("title") or source_id,
        display_text=record.get("transient_text") or record.get("abstract") or "",
        authors=list(record.get("authors") or []),
        categories=list(record.get("categories") or []),
        published_at=record.get("published_at"),
        html_url=record.get("html_url"),
        landing_url=record.get("landing_url"),
        source_url=record.get("source_url") or record.get("landing_url"),
        arxiv_id=record.get("arxiv_id") if source_type == "arxiv" else None,
        metadata=record.get("source_metadata") or {},
    )
