"""Sync public R2 indexes into the app SQLite database."""

from __future__ import annotations

import logging
from datetime import date
from sqlalchemy.orm import Session
from tqdm import tqdm

from app.core.config import settings
from app.db.session import SessionLocal, engine
from app.models import Base
from app.services.daily_dates import DAILY_SEARCH_DATE_SET
from app.services.daily_index_store import upsert_arxiv_day, upsert_lesswrong_day
from app.services.r2_index_fetch import fetch_manifest, items_for_date

logger = logging.getLogger(__name__)


def sync_public_indexes(*, progress: tqdm | None = None) -> dict[str, dict[str, tuple[int, int]]]:
    Base.metadata.create_all(bind=engine)

    summary: dict[str, dict[str, tuple[int, int]]] = {"arxiv": {}, "lesswrong": {}}
    scanned_total = 0
    db = SessionLocal()
    try:
        summary["arxiv"], scanned_total = _sync_source(
            db,
            source_type="arxiv",
            public_base_url=settings.ARXIV_HTML_PUBLIC_BASE_URL,
            manifest_path=settings.ARXIV_HTML_INDEX_PATH,
            items_key="papers",
            upsert_day=upsert_arxiv_day,
            progress=progress,
            scanned_total=scanned_total,
        )
        summary["lesswrong"], scanned_total = _sync_source(
            db,
            source_type="lesswrong",
            public_base_url=settings.LESSWRONG_HTML_PUBLIC_BASE_URL,
            manifest_path=settings.LESSWRONG_HTML_INDEX_PATH,
            items_key="posts",
            upsert_day=upsert_lesswrong_day,
            progress=progress,
            scanned_total=scanned_total,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return summary


def _sync_source(
    db: Session,
    *,
    source_type: str,
    public_base_url: str,
    manifest_path: str,
    items_key: str,
    upsert_day,
    progress: tqdm | None = None,
    scanned_total: int = 0,
) -> tuple[dict[str, tuple[int, int]], int]:
    manifest = fetch_manifest(
        public_base_url=public_base_url,
        manifest_path=manifest_path,
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
            total, searchable, _skipped = upsert_arxiv_day(
                db, run_date=run_date, shard_items=shard_items
            )
        else:
            total, searchable = upsert_day(db, run_date=run_date, shard_items=shard_items)
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
