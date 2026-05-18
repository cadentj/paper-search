"""SQLite-backed daily index reads."""

from __future__ import annotations

from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.paper import Paper
from app.services.source_types import SourceFetchResult


def count_for_date(db: Session, *, source_type: str, run_date: date) -> int:
    return _papers_for_date(db, source_type=source_type, run_date=run_date).count()


def candidates_for_date(
    db: Session, *, source_type: str, run_date: date
) -> SourceFetchResult:
    rows = _papers_for_date(db, source_type=source_type, run_date=run_date).all()
    return SourceFetchResult(papers=rows)


def _papers_for_date(db: Session, *, source_type: str, run_date: date):
    return db.query(Paper).filter(
        Paper.source_type == source_type,
        func.date(Paper.published_at) == run_date,
    )
