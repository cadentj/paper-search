"""Generic source provider registry for daily search inputs."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from app.models.paper import Paper
from app.services.paper_html_source import arxiv_html_url, read_paper_html
from app.services.html_parser import prepare_arxiv_html_for_viewer
from app.services.public_arxiv_cache import fetch_index, fetch_public_cached_papers
from app.services.public_lesswrong_cache import (
    available_counts as lesswrong_available_counts,
    fetch_public_cached_posts,
    fetch_public_post_html,
)

logger = logging.getLogger(__name__)


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


class SourceProvider(Protocol):
    source_type: str

    def counts_by_date(self, dates: list[date]) -> dict[str, int]:
        ...

    def candidates_for_date(self, run_date: date) -> SourceFetchResult:
        ...

    def html_for_paper(self, paper: Paper) -> dict[str, str | None]:
        ...


class ArxivProvider:
    source_type = "arxiv"

    def counts_by_date(self, dates: list[date]) -> dict[str, int]:
        try:
            index = fetch_index()
        except Exception:
            logger.exception("failed to fetch arXiv index for available dates")
            return {}
        valid_dates = {day.isoformat() for day in dates}
        return {
            str(day): int(payload.get("count") or 0)
            for day, payload in (index.get("dates") or {}).items()
            if str(day) in valid_dates
        }

    def candidates_for_date(self, run_date: date) -> SourceFetchResult:
        try:
            records = fetch_public_cached_papers(run_date=run_date.isoformat())
        except Exception as exc:
            logger.exception("failed to fetch cached arXiv papers for %s", run_date)
            return SourceFetchResult(items=[], errors=[f"arXiv fetch failed: {exc}"])
        return SourceFetchResult(items=[candidate_from_record(record) for record in records])

    def html_for_paper(self, paper: Paper) -> dict[str, str | None]:
        paper_html = read_paper_html(paper.arxiv_id, html_url=paper.html_url)
        if paper_html:
            return {
                "html": prepare_arxiv_html_for_viewer(
                    paper_html.html,
                    paper_html.source_url,
                ),
                "source_url": paper_html.source_url,
            }
        return {
            "html": None,
            "source_url": arxiv_html_url(paper.arxiv_id) if paper.arxiv_id else None,
        }


class LessWrongProvider:
    source_type = "lesswrong"

    def counts_by_date(self, dates: list[date]) -> dict[str, int]:
        try:
            counts = lesswrong_available_counts()
        except Exception:
            logger.exception("failed to fetch LessWrong counts for available dates")
            return {}
        valid_dates = {day.isoformat() for day in dates}
        return {day: count for day, count in counts.items() if day in valid_dates}

    def candidates_for_date(self, run_date: date) -> SourceFetchResult:
        try:
            records = fetch_public_cached_posts(run_date=run_date.isoformat())
        except Exception as exc:
            logger.exception("failed to fetch cached LessWrong posts for %s", run_date)
            return SourceFetchResult(items=[], errors=[f"LessWrong fetch failed: {exc}"])
        return SourceFetchResult(items=[candidate_from_record(record) for record in records])

    def html_for_paper(self, paper: Paper) -> dict[str, str | None]:
        try:
            html = fetch_public_post_html(
                html_url=paper.html_url,
                html_key=(paper.source_metadata or {}).get("html_key"),
            )
        except Exception:
            logger.exception("failed to fetch LessWrong HTML for paper=%s", paper.id)
            html = None
        return {
            "html": html,
            "source_url": paper.source_url or paper.landing_url,
        }


PROVIDERS: dict[str, SourceProvider] = {
    "arxiv": ArxivProvider(),
    "lesswrong": LessWrongProvider(),
}


def provider_for(source_type: str) -> SourceProvider | None:
    return PROVIDERS.get(source_type)


def counts_by_source_for_dates(
    source_types: set[str],
    dates: list[date],
) -> dict[str, dict[str, int]]:
    return {
        source_type: provider.counts_by_date(dates)
        for source_type, provider in PROVIDERS.items()
        if source_type in source_types
    }


def candidates_for_sources(
    source_types: set[str],
    run_date: date,
) -> SourceFetchResult:
    items: list[CandidateItem] = []
    errors: list[str] = []
    for source_type in sorted(source_types):
        provider = provider_for(source_type)
        if not provider:
            errors.append(f"Unknown source provider: {source_type}")
            continue
        result = provider.candidates_for_date(run_date)
        items.extend(result.items)
        errors.extend(result.errors)
    return SourceFetchResult(items=items, errors=errors)


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
