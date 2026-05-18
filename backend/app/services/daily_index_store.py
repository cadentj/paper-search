"""SQLite-backed daily index reads and writes."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.paper import Paper
from app.services.index_records import (
    arxiv_matches_categories,
    arxiv_record_from_shard,
    arxiv_is_searchable,
    lesswrong_is_searchable,
    lesswrong_record_from_shard,
    settings_arxiv_categories,
)
from app.services.source_types import CandidateItem, SourceFetchResult


def count_for_date(db: Session, *, source_type: str, run_date: date) -> int:
    return _papers_for_date(db, source_type=source_type, run_date=run_date).count()


def candidates_for_date(
    db: Session, *, source_type: str, run_date: date
) -> SourceFetchResult:
    rows = _papers_for_date(db, source_type=source_type, run_date=run_date).all()
    items = [_candidate_from_paper(paper) for paper in rows]
    return SourceFetchResult(items=items)


def _papers_for_date(db: Session, *, source_type: str, run_date: date):
    return db.query(Paper).filter(
        Paper.source_type == source_type,
        func.date(Paper.published_at) == run_date,
    )


def _candidate_from_paper(paper: Paper) -> CandidateItem:
    return CandidateItem(
        source_type=paper.source_type,
        source_id=paper.source_id or "",
        title=paper.title,
        display_text=paper.search_text or paper.abstract or "",
        authors=list(paper.authors or []),
        categories=list(paper.categories or []),
        published_at=paper.published_at,
        html_url=paper.html_url,
        source_url=paper.source_url,
    )


def upsert_arxiv_day(
    db: Session,
    *,
    run_date: date,
    shard_items: list[dict[str, Any]],
) -> tuple[int, int, int]:
    """Load papers for one arXiv shard day. Returns (total, searchable, skipped_category)."""
    category_set = set(settings_arxiv_categories())
    now = datetime.now(timezone.utc)
    total = len(shard_items)
    skipped_category = 0
    records: list[dict[str, Any]] = []

    for paper in shard_items:
        arxiv_id = str(paper.get("arxiv_id") or "")
        if not arxiv_id:
            continue
        if not arxiv_is_searchable(paper):
            continue
        if not arxiv_matches_categories(paper, category_set):
            skipped_category += 1
            continue

        record = arxiv_record_from_shard(paper)
        _ensure_published_on_run_date(record, run_date=run_date)
        records.append(record)

    max_results = settings.ARXIV_PUBLIC_DAILY_LIMIT
    if max_results and max_results > 0 and len(records) > max_results:
        records = records[:max_results]

    searchable = len(records)
    for record in records:
        _upsert_paper(db, record=record, now=now)

    return total, searchable, skipped_category


def upsert_lesswrong_day(
    db: Session,
    *,
    run_date: date,
    shard_items: list[dict[str, Any]],
) -> tuple[int, int]:
    """Returns (total, searchable)."""
    now = datetime.now(timezone.utc)
    total = len(shard_items)
    searchable = 0

    for post in shard_items:
        post_id = str(post.get("post_id") or "")
        if not post_id:
            continue
        if not lesswrong_is_searchable(post):
            continue

        record = lesswrong_record_from_shard(post)
        _ensure_published_on_run_date(record, run_date=run_date)
        _upsert_paper(db, record=record, now=now)
        searchable += 1

    return total, searchable


def _ensure_published_on_run_date(record: dict[str, Any], *, run_date: date) -> None:
    published_at = record.get("published_at")
    if published_at is None or published_at.date() != run_date:
        record["published_at"] = datetime.combine(
            run_date, time.min, tzinfo=timezone.utc
        )


def _upsert_paper(db: Session, *, record: dict[str, Any], now: datetime) -> Paper:
    source_type = record["source_type"]
    source_id = record["source_id"]
    existing = (
        db.query(Paper)
        .filter(Paper.source_type == source_type, Paper.source_id == source_id)
        .first()
    )
    if existing:
        existing.source_type = source_type
        existing.source_id = source_id
        existing.title = record["title"]
        existing.abstract = record["abstract"]
        existing.search_text = record.get("search_text") or ""
        existing.authors = record.get("authors") or []
        existing.categories = record.get("categories") or []
        existing.published_at = record.get("published_at")
        existing.html_url = record.get("html_url")
        existing.source_url = record.get("source_url")
        existing.updated_at = now
        return existing

    paper = Paper(
        id=str(uuid.uuid4()),
        source_type=source_type,
        source_id=source_id,
        title=record["title"],
        abstract=record["abstract"],
        search_text=record.get("search_text") or "",
        authors=record.get("authors") or [],
        categories=record.get("categories") or [],
        published_at=record.get("published_at"),
        html_url=record.get("html_url"),
        source_url=record.get("source_url"),
        created_at=now,
        updated_at=now,
    )
    db.add(paper)
    return paper
