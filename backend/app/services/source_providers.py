"""Generic source provider registry for daily search inputs."""

from __future__ import annotations

from datetime import date

from app.services.arxiv_provider import ArxivProvider
from app.services.lesswrong_provider import LessWrongProvider
from app.services.source_types import (
    CandidateItem,
    SourceFetchResult,
    SourceProvider,
    candidate_from_record,
)

__all__ = [
    "CandidateItem",
    "SourceFetchResult",
    "SourceProvider",
    "candidate_from_record",
    "provider_for",
    "counts_by_source_for_date",
    "candidates_for_sources",
]

PROVIDERS: dict[str, SourceProvider] = {
    "arxiv": ArxivProvider(),
    "lesswrong": LessWrongProvider(),
}


def provider_for(source_type: str) -> SourceProvider | None:
    return PROVIDERS.get(source_type)


def counts_by_source_for_date(source_types: set[str], run_date: date) -> dict[str, int]:
    counts: dict[str, int] = {}
    for source_type in sorted(source_types):
        provider = provider_for(source_type)
        if provider:
            counts[source_type] = provider.count_for_date(run_date)
    return counts


def candidates_for_sources(
    source_types: set[str],
    run_date: date,
) -> SourceFetchResult:
    items: list[CandidateItem] = []
    errors: list[str] = []
    skipped_missing_text: dict[str, int] = {}
    for source_type in sorted(source_types):
        provider = provider_for(source_type)
        if not provider:
            errors.append(f"Unknown source provider: {source_type}")
            continue
        result = provider.candidates_for_date(run_date)
        items.extend(result.items)
        errors.extend(result.errors)
        for key, value in result.skipped_missing_text.items():
            skipped_missing_text[key] = skipped_missing_text.get(key, 0) + value
    return SourceFetchResult(
        items=items,
        errors=errors,
        skipped_missing_text=skipped_missing_text,
    )
