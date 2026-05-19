#!/usr/bin/env python3
"""Pull public R2 indexes into the app SQLite database."""

from __future__ import annotations

import logging
import sys
import uuid
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from tqdm import tqdm

from paper_search_core.daily_dates import DAILY_SEARCH_DATE_SET
from paper_search_core.index_records import (
    IndexSettings,
    arxiv_categories,
    arxiv_is_searchable,
    arxiv_matches_categories,
    arxiv_record_from_shard,
    lesswrong_is_searchable,
    lesswrong_record_from_shard,
)
from paper_search_core.models import Base, SQLAPaper

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from r2 import (  # noqa: E402
    Settings,
    fetch_manifest,
    items_for_date,
    resolve_sqlite_path,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
for _logger_name in ("httpx", "httpcore"):
    logging.getLogger(_logger_name).setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def load_arxiv_day(
    db: Session,
    run_date: date,
    shard_items: list[dict[str, Any]],
    settings: IndexSettings,
    arxiv_public_daily_limit: int = 0,
) -> tuple[int, int, int]:
    category_set = set(arxiv_categories(settings))
    now = datetime.now(timezone.utc)
    total = len(shard_items)
    skipped_category = 0
    records: list[dict[str, Any]] = []

    for paper in shard_items:
        arxiv_id = str(paper.get("arxiv_id") or "")
        if not arxiv_id or not arxiv_is_searchable(paper):
            continue
        if not arxiv_matches_categories(paper, category_set):
            skipped_category += 1
            continue
        record = arxiv_record_from_shard(paper, settings)
        _ensure_published_on_run_date(record, run_date=run_date)
        records.append(record)

    if arxiv_public_daily_limit > 0 and len(records) > arxiv_public_daily_limit:
        records = records[:arxiv_public_daily_limit]

    searchable = len(records)
    for record in records:
        _insert_paper(db, record=record, now=now)

    return total, searchable, skipped_category


def load_lesswrong_day(
    db: Session,
    run_date: date,
    shard_items: list[dict[str, Any]],
    settings: IndexSettings,
) -> tuple[int, int]:
    now = datetime.now(timezone.utc)
    total = len(shard_items)
    searchable = 0

    for post in shard_items:
        post_id = str(post.get("post_id") or "")
        if not post_id or not lesswrong_is_searchable(post):
            continue
        record = lesswrong_record_from_shard(post, settings)
        _ensure_published_on_run_date(record, run_date=run_date)
        _insert_paper(db, record=record, now=now)
        searchable += 1

    return total, searchable


def _ensure_published_on_run_date(record: dict[str, Any], run_date: date) -> None:
    published_at = record.get("published_at")
    if published_at is None or published_at.date() != run_date:
        record["published_at"] = datetime.combine(
            run_date, time.min, tzinfo=timezone.utc
        )


def _require_empty_paper_table(db: Session) -> None:
    count = db.query(SQLAPaper).count()
    if count:
        raise RuntimeError(
            f"Refusing to sync: database already has {count} paper(s). "
            "Use an empty database before running sync."
        )


def _insert_paper(db: Session, record: dict[str, Any], now: datetime) -> SQLAPaper:
    source_type = record["source_type"]
    source_id = record["source_id"]
    existing = (
        db.query(SQLAPaper)
        .filter(SQLAPaper.source_type == source_type, SQLAPaper.source_id == source_id)
        .first()
    )
    if existing:
        return existing

    paper = SQLAPaper(
        id=str(uuid.uuid4()),
        source_type=source_type,
        source_id=source_id,
        title=record["title"],
        search_text=record.get("search_text") or "",
        authors=record.get("authors") or [],
        published_at=record.get("published_at"),
        html_url=record.get("html_url"),
        source_url=record.get("source_url"),
        created_at=now,
    )
    db.add(paper)
    from app.services.papers_fts import index_paper

    index_paper(db, paper)
    return paper


def sync_public_indexes(
    settings: Settings,
    progress: tqdm | None = None,
) -> dict[str, dict[str, tuple[int, int]]]:
    settings.require_sync_urls()
    db_path = resolve_sqlite_path(settings.DATABASE_URL)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    from app.services.papers_fts import ensure_papers_fts

    ensure_papers_fts(engine)
    session_factory = sessionmaker(bind=engine)
    index_settings = settings.index_settings()

    summary: dict[str, dict[str, tuple[int, int]]] = {"arxiv": {}, "lesswrong": {}}
    scanned_total = 0
    db = session_factory()
    try:
        _require_empty_paper_table(db)
        summary["arxiv"], scanned_total = _sync_source(
            db,
            source_type="arxiv",
            public_base_url=settings.ARXIV_HTML_PUBLIC_BASE_URL,
            manifest_path=settings.ARXIV_HTML_INDEX_PATH,
            items_key="papers",
            settings=index_settings,
            arxiv_public_daily_limit=settings.ARXIV_PUBLIC_DAILY_LIMIT,
            progress=progress,
            scanned_total=scanned_total,
        )
        summary["lesswrong"], scanned_total = _sync_source(
            db,
            source_type="lesswrong",
            public_base_url=settings.LESSWRONG_HTML_PUBLIC_BASE_URL,
            manifest_path=settings.LESSWRONG_HTML_INDEX_PATH,
            items_key="posts",
            settings=index_settings,
            arxiv_public_daily_limit=0,
            progress=progress,
            scanned_total=scanned_total,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
        engine.dispose()
    return summary


def _sync_source(
    db: Session,
    source_type: str,
    public_base_url: str,
    manifest_path: str,
    items_key: str,
    settings: IndexSettings,
    arxiv_public_daily_limit: int,
    progress: tqdm | None,
    scanned_total: int,
) -> tuple[dict[str, tuple[int, int]], int]:
    manifest = fetch_manifest(
        public_base_url=public_base_url, manifest_path=manifest_path
    )
    dates = manifest.get("dates") or {}
    per_date: dict[str, tuple[int, int]] = {}

    for run_date in sorted(DAILY_SEARCH_DATE_SET):
        date_key = run_date.isoformat()
        date_payload = dates.get(date_key)
        if not date_payload:
            message = f"{source_type}: no manifest entry for {date_key}"
            if progress is not None:
                tqdm.write(message)
            else:
                logger.warning("%s", message)
            per_date[date_key] = (0, 0)
            if progress is not None:
                progress.update(1)
                _set_sync_progress(progress, source_type, 0, scanned_total)
            continue

        shard_items = items_for_date(
            public_base_url=public_base_url,
            run_date=date_key,
            date_payload=date_payload,
            items_key=items_key,
        )
        if source_type == "arxiv":
            total, searchable, _ = load_arxiv_day(
                db,
                run_date=run_date,
                shard_items=shard_items,
                settings=settings,
                arxiv_public_daily_limit=arxiv_public_daily_limit,
            )
        else:
            total, searchable = load_lesswrong_day(
                db,
                run_date=run_date,
                shard_items=shard_items,
                settings=settings,
            )
        per_date[date_key] = (total, searchable)
        scanned_total += total
        if progress is not None:
            progress.update(1)
            _set_sync_progress(progress, source_type, total, scanned_total)
        else:
            logger.info(
                "%s %s: total=%s searchable=%s",
                source_type,
                date_key,
                total,
                searchable,
            )

    return per_date, scanned_total


def _set_sync_progress(
    progress: tqdm,
    source_type: str,
    last_scanned: int,
    scanned_total: int,
) -> None:
    progress.set_postfix(source=source_type, last=last_scanned, total=scanned_total)


def main() -> None:
    settings = Settings()
    db_path = resolve_sqlite_path(settings.DATABASE_URL)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    date_slots = len(DAILY_SEARCH_DATE_SET)
    with tqdm(
        total=date_slots * 2,
        desc="syncing public index",
        unit="date",
        dynamic_ncols=True,
    ) as progress:
        summary = sync_public_indexes(settings, progress=progress)

    for source_type, dates in summary.items():
        synced = sum(1 for total, _ in dates.values() if total > 0)
        logger.info(
            "%s: synced %s dates (%s total date slots in window)",
            source_type,
            synced,
            len(dates),
        )


if __name__ == "__main__":
    main()
