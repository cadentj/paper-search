"""Generic source provider registry for daily search inputs."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.models.paper import Paper
from app.services.arxiv_provider import ArxivProvider
from app.services.lesswrong_provider import LessWrongProvider
from app.services.source_types import SourceProvider

__all__ = [
    "SourceProvider",
    "provider_for",
    "counts_by_source_for_date",
    "papers_for_sources",
]

PROVIDERS: dict[str, SourceProvider] = {
    "arxiv": ArxivProvider(),
    "lesswrong": LessWrongProvider(),
}


def provider_for(source_type: str) -> SourceProvider | None:
    return PROVIDERS.get(source_type)


def counts_by_source_for_date(
    db: Session, source_types: set[str], run_date: date
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for source_type in sorted(source_types):
        provider = provider_for(source_type)
        if provider:
            counts[source_type] = provider.count_for_date(db, run_date)
    return counts


def papers_for_sources(
    db: Session, source_types: set[str], run_date: date
) -> list[Paper]:
    papers: list[Paper] = []
    for source_type in sorted(source_types):
        provider = provider_for(source_type)
        if not provider:
            raise ValueError(f"Unknown source provider: {source_type}")
        papers.extend(provider.papers_for_date(db, run_date))
    return papers
