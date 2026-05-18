"""SQLite-backed daily index reads and writes."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.paper import Paper
from app.models.source_daily import SourceDailyCandidate, SourceDailyRollup
from app.services.index_records import (
    arxiv_matches_categories,
    arxiv_record_from_shard,
    arxiv_is_searchable,
    lesswrong_is_searchable,
    lesswrong_record_from_shard,
    settings_arxiv_categories,
)
from app.services.source_types import CandidateItem, SourceFetchResult


def rollup_count(db: Session, *, source_type: str, run_date: date) -> int:
    row = (
        db.query(SourceDailyRollup)
        .filter(
            SourceDailyRollup.source_type == source_type,
            SourceDailyRollup.run_date == run_date,
        )
        .first()
    )
    if row is None:
        return 0
    return int(row.searchable_count or 0)


def candidates_for_date(
    db: Session, *, source_type: str, run_date: date
) -> SourceFetchResult:
    rows = (
        db.query(Paper)
        .join(
            SourceDailyCandidate,
            SourceDailyCandidate.paper_id == Paper.id,
        )
        .filter(
            SourceDailyCandidate.source_type == source_type,
            SourceDailyCandidate.run_date == run_date,
        )
        .all()
    )
    items = [_candidate_from_paper(paper) for paper in rows]
    return SourceFetchResult(items=items)


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
        landing_url=paper.landing_url,
        source_url=paper.source_url or paper.landing_url,
        arxiv_id=paper.arxiv_id if paper.source_type == "arxiv" else None,
        metadata=dict(paper.source_metadata or {}),
    )


def upsert_arxiv_day(
    db: Session,
    *,
    run_date: date,
    shard_items: list[dict[str, Any]],
) -> tuple[int, int, int]:
    """Upsert papers and daily index rows. Returns (total, searchable, skipped_category)."""
    category_set = set(settings_arxiv_categories())
    now = datetime.now(timezone.utc)
    total = len(shard_items)
    searchable = 0
    skipped_category = 0
    candidate_rows: list[SourceDailyCandidate] = []

    db.query(SourceDailyCandidate).filter(
        SourceDailyCandidate.source_type == "arxiv",
        SourceDailyCandidate.run_date == run_date,
    ).delete()

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
        paper_row = _upsert_paper(db, record=record, now=now)
        searchable += 1
        candidate_rows.append(
            SourceDailyCandidate(
                source_type="arxiv",
                run_date=run_date,
                source_id=record["source_id"],
                paper_id=paper_row.id,
            )
        )

    max_results = settings.ARXIV_PUBLIC_DAILY_LIMIT
    if max_results and max_results > 0 and len(candidate_rows) > max_results:
        candidate_rows = candidate_rows[:max_results]
        searchable = len(candidate_rows)

    for row in candidate_rows:
        db.add(row)

    _upsert_rollup(
        db,
        source_type="arxiv",
        run_date=run_date,
        total_count=total,
        searchable_count=searchable,
        synced_at=now,
    )
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

    db.query(SourceDailyCandidate).filter(
        SourceDailyCandidate.source_type == "lesswrong",
        SourceDailyCandidate.run_date == run_date,
    ).delete()

    for post in shard_items:
        post_id = str(post.get("post_id") or "")
        if not post_id:
            continue
        if not lesswrong_is_searchable(post):
            continue

        record = lesswrong_record_from_shard(post)
        paper_row = _upsert_paper(db, record=record, now=now)
        searchable += 1
        db.add(
            SourceDailyCandidate(
                source_type="lesswrong",
                run_date=run_date,
                source_id=record["source_id"],
                paper_id=paper_row.id,
            )
        )

    _upsert_rollup(
        db,
        source_type="lesswrong",
        run_date=run_date,
        total_count=total,
        searchable_count=searchable,
        synced_at=now,
    )
    return total, searchable


def _upsert_paper(db: Session, *, record: dict[str, Any], now: datetime) -> Paper:
    source_type = record["source_type"]
    source_id = record["source_id"]
    existing = (
        db.query(Paper)
        .filter(Paper.source_type == source_type, Paper.source_id == source_id)
        .first()
    )
    if not existing and source_type == "arxiv":
        existing = db.query(Paper).filter(Paper.arxiv_id == record.get("arxiv_id")).first()

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
        existing.landing_url = record.get("landing_url")
        existing.source_url = record.get("source_url") or record.get("landing_url")
        existing.source_metadata = record.get("source_metadata") or {}
        existing.updated_at = now
        if source_type == "arxiv":
            existing.arxiv_id = record.get("arxiv_id")
        return existing

    paper = Paper(
        id=str(uuid.uuid4()),
        arxiv_id=record.get("arxiv_id") if source_type == "arxiv" else None,
        source_type=source_type,
        source_id=source_id,
        title=record["title"],
        abstract=record["abstract"],
        search_text=record.get("search_text") or "",
        authors=record.get("authors") or [],
        categories=record.get("categories") or [],
        published_at=record.get("published_at"),
        html_url=record.get("html_url"),
        landing_url=record.get("landing_url"),
        source_url=record.get("source_url") or record.get("landing_url"),
        source_metadata=record.get("source_metadata") or {},
        created_at=now,
        updated_at=now,
    )
    db.add(paper)
    return paper


def _upsert_rollup(
    db: Session,
    *,
    source_type: str,
    run_date: date,
    total_count: int,
    searchable_count: int,
    synced_at: datetime,
) -> None:
    row = (
        db.query(SourceDailyRollup)
        .filter(
            SourceDailyRollup.source_type == source_type,
            SourceDailyRollup.run_date == run_date,
        )
        .first()
    )
    if row:
        row.total_count = total_count
        row.searchable_count = searchable_count
        row.synced_at = synced_at
        return

    db.add(
        SourceDailyRollup(
            source_type=source_type,
            run_date=run_date,
            total_count=total_count,
            searchable_count=searchable_count,
            synced_at=synced_at,
        )
    )
