"""Shared arXiv R2 index manifest and date-shard helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Iterator

from r2_index import (
    date_index_key as _date_index_key,
    json_body,
    normalize_prefix,
    upload_sharded_index,
)

DEFAULT_HTML_PREFIX = "data/"
DEFAULT_INDEX_KEY = "data/index/papers-by-date.json"
DEFAULT_DATE_INDEX_PREFIX = "data/index/dates/"
SCHEMA_VERSION = 3


def date_index_key(*, date: str, date_index_prefix: str) -> str:
    return _date_index_key(date=date, date_index_prefix=date_index_prefix)


def is_sharded_manifest(index: dict[str, Any]) -> bool:
    dates = index.get("dates") or {}
    if not dates:
        return False
    sample = next(iter(dates.values()))
    return isinstance(sample, dict) and "index_key" in sample and "papers" not in sample


def is_monolithic_index(index: dict[str, Any]) -> bool:
    dates = index.get("dates") or {}
    if not dates:
        return False
    sample = next(iter(dates.values()))
    return isinstance(sample, dict) and isinstance(sample.get("papers"), list)


def iter_date_papers(
    index: dict[str, Any],
    *,
    load_date_index: Callable[[str], dict[str, Any]] | None = None,
) -> Iterator[tuple[str, dict[str, Any]]]:
    for day, date_payload in (index.get("dates") or {}).items():
        if not isinstance(date_payload, dict):
            continue
        inline_papers = date_payload.get("papers")
        if isinstance(inline_papers, list):
            for paper in inline_papers:
                if isinstance(paper, dict):
                    yield day, paper
            continue

        index_key = str(date_payload.get("index_key") or "")
        if not index_key or load_date_index is None:
            continue

        date_index = load_date_index(index_key)
        for paper in date_index.get("papers") or []:
            if isinstance(paper, dict):
                yield day, paper


def collect_papers_missing_abstract(
    index: dict[str, Any],
    *,
    load_date_index: Callable[[str], dict[str, Any]] | None = None,
    normalize_arxiv_id: Callable[[str], str],
    html_key_for_arxiv_id: Callable[[str], str],
) -> list[dict[str, str]]:
    missing: list[dict[str, str]] = []
    seen: set[str] = set()
    for _, paper in iter_date_papers(index, load_date_index=load_date_index):
        arxiv_id = normalize_arxiv_id(str(paper.get("arxiv_id") or ""))
        if not arxiv_id or arxiv_id in seen:
            continue
        seen.add(arxiv_id)
        if str(paper.get("abstract") or "").strip():
            continue
        missing.append(
            {
                "arxiv_id": arxiv_id,
                "html_key": str(paper.get("html_key") or html_key_for_arxiv_id(arxiv_id)),
            }
        )
    return missing


def apply_metadata_to_index(
    index: dict[str, Any],
    metadata_by_id: dict[str, dict[str, Any]],
    *,
    load_date_index: Callable[[str], dict[str, Any]] | None = None,
    store_date_index: Callable[[str, dict[str, Any]], None] | None = None,
    normalize_arxiv_id: Callable[[str], str],
) -> tuple[int, int]:
    enriched = 0
    unresolved = 0

    dates = index.get("dates") or {}
    for day, date_payload in dates.items():
        if not isinstance(date_payload, dict):
            continue

        inline_papers = date_payload.get("papers")
        if isinstance(inline_papers, list):
            for paper in inline_papers:
                result = _apply_metadata_to_paper(paper, metadata_by_id, normalize_arxiv_id)
                if result == "enriched":
                    enriched += 1
                elif result == "unresolved":
                    unresolved += 1
            continue

        index_key = str(date_payload.get("index_key") or "")
        if not index_key or load_date_index is None or store_date_index is None:
            continue

        date_index = load_date_index(index_key)
        for paper in date_index.get("papers") or []:
            result = _apply_metadata_to_paper(paper, metadata_by_id, normalize_arxiv_id)
            if result == "enriched":
                enriched += 1
            elif result == "unresolved":
                unresolved += 1
        store_date_index(index_key, date_index)

    return enriched, unresolved


def _apply_metadata_to_paper(
    paper: dict[str, Any],
    metadata_by_id: dict[str, dict[str, Any]],
    normalize_arxiv_id: Callable[[str], str],
) -> str | None:
    arxiv_id = normalize_arxiv_id(str(paper.get("arxiv_id") or ""))
    if not arxiv_id or str(paper.get("abstract") or "").strip():
        return None

    metadata = metadata_by_id.get(arxiv_id)
    if not metadata:
        return "unresolved"

    paper["title"] = paper.get("title") or metadata.get("title") or arxiv_id
    paper["abstract"] = metadata.get("abstract") or ""
    paper["authors"] = metadata.get("authors") or []
    return "enriched"


def split_monolithic_to_sharded(
    index: dict[str, Any],
    *,
    html_prefix: str = DEFAULT_HTML_PREFIX,
    date_index_prefix: str = DEFAULT_DATE_INDEX_PREFIX,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    generated_at = datetime.now(timezone.utc).isoformat()
    normalized_date_prefix = normalize_prefix(date_index_prefix)
    manifest_dates: dict[str, dict[str, Any]] = {}
    date_shards: dict[str, dict[str, Any]] = {}

    dates = index.get("dates") or {}
    for day in sorted(dates.keys(), reverse=True):
        date_payload = dates[day]
        if not isinstance(date_payload, dict):
            continue

        papers = date_payload.get("papers")
        if not isinstance(papers, list):
            index_key = str(date_payload.get("index_key") or "")
            if not index_key:
                continue
            manifest_dates[day] = {
                "count": int(date_payload.get("count") or 0),
                "index_key": index_key,
            }
            continue

        sorted_papers = sorted(papers, key=lambda item: str(item.get("arxiv_id") or ""))
        index_key = date_index_key(date=day, date_index_prefix=normalized_date_prefix)
        manifest_dates[day] = {"count": len(sorted_papers), "index_key": index_key}
        date_shards[day] = {
            "schema_version": SCHEMA_VERSION,
            "source": "arxiv",
            "date": day,
            "generated_at": generated_at,
            "count": len(sorted_papers),
            "papers": sorted_papers,
        }

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "source": "arxiv",
        "generated_at": generated_at,
        "html_prefix": normalize_prefix(html_prefix or index.get("html_prefix") or DEFAULT_HTML_PREFIX),
        "date_index_prefix": normalized_date_prefix,
        "skipped_missing_files": int(index.get("skipped_missing_files") or 0),
        "total_papers": sum(day["count"] for day in manifest_dates.values()),
        "dates": manifest_dates,
    }
    if index.get("metadata_enriched_at"):
        manifest["metadata_enriched_at"] = index["metadata_enriched_at"]
    return manifest, date_shards


def build_sharded_index_from_daily_papers(
    daily_papers: dict[str, list[dict[str, Any]]],
    *,
    html_prefix: str = DEFAULT_HTML_PREFIX,
    date_index_prefix: str = DEFAULT_DATE_INDEX_PREFIX,
    skipped_missing_files: int = 0,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    generated_at = datetime.now(timezone.utc).isoformat()
    normalized_date_prefix = normalize_prefix(date_index_prefix)
    manifest_dates: dict[str, dict[str, Any]] = {}
    date_shards: dict[str, dict[str, Any]] = {}

    for day in sorted(daily_papers.keys(), reverse=True):
        papers = sorted(daily_papers[day], key=lambda item: str(item.get("arxiv_id") or ""))
        index_key = date_index_key(date=day, date_index_prefix=normalized_date_prefix)
        manifest_dates[day] = {"count": len(papers), "index_key": index_key}
        date_shards[day] = {
            "schema_version": SCHEMA_VERSION,
            "source": "arxiv",
            "date": day,
            "generated_at": generated_at,
            "count": len(papers),
            "papers": papers,
        }

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "source": "arxiv",
        "generated_at": generated_at,
        "html_prefix": normalize_prefix(html_prefix),
        "date_index_prefix": normalized_date_prefix,
        "skipped_missing_files": skipped_missing_files,
        "total_papers": sum(day["count"] for day in manifest_dates.values()),
        "dates": manifest_dates,
    }
    return manifest, date_shards


def count_papers(index: dict[str, Any]) -> int:
    if index.get("total_papers") is not None:
        return int(index["total_papers"])
    return sum(
        int((payload or {}).get("count") or len((payload or {}).get("papers") or []))
        for payload in (index.get("dates") or {}).values()
    )


__all__ = [
    "DEFAULT_DATE_INDEX_PREFIX",
    "DEFAULT_HTML_PREFIX",
    "DEFAULT_INDEX_KEY",
    "SCHEMA_VERSION",
    "apply_metadata_to_index",
    "build_sharded_index_from_daily_papers",
    "collect_papers_missing_abstract",
    "count_papers",
    "date_index_key",
    "is_monolithic_index",
    "is_sharded_manifest",
    "iter_date_papers",
    "json_body",
    "split_monolithic_to_sharded",
    "normalize_prefix",
    "upload_sharded_index",
]