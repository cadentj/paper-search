"""Daily search sources: index reads, HTML, and SQLADataSource settings."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

import httpx
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.data_source import SQLADataSource
from app.models.paper import SQLAPaper
from app.services.errors import NotFound
from app.utils.html_parser import prepare_arxiv_html_for_viewer

logger = logging.getLogger(__name__)

DEFAULT_SOURCES = {
    "arxiv": {
        "name": "arXiv",
        "enabled": True,
        "settings": {},
    },
    "lesswrong": {
        "name": "LessWrong",
        "enabled": False,
        "settings": {
            "view": "new",
        },
    },
}

KNOWN_SOURCE_TYPES = frozenset(DEFAULT_SOURCES)


def _papers_query(db: Session, source_type: str, run_date: date):
    return db.query(SQLAPaper).filter(
        SQLAPaper.source_type == source_type,
        func.date(SQLAPaper.published_at) == run_date,
    )


def count_papers_for_source(db: Session, source_type: str, run_date: date) -> int:
    try:
        return _papers_query(db, source_type, run_date).count()
    except Exception:
        logger.exception(
            "failed to read %s index count for %s", source_type, run_date
        )
        return 0


def papers_for_source(db: Session, source_type: str, run_date: date) -> list[SQLAPaper]:
    return _papers_query(db, source_type, run_date).all()


def _fetch_url_text(url: str) -> str | None:
    try:
        response = httpx.get(url, timeout=30.0, follow_redirects=True)
        response.raise_for_status()
        return response.text
    except httpx.HTTPError:
        return None


def _default_paper_html(paper: SQLAPaper) -> dict[str, str | None]:
    return {
        "html": _fetch_url_text(paper.html_url) if paper.html_url else None,
        "source_url": paper.source_url,
    }


def _arxiv_paper_html(paper: SQLAPaper) -> dict[str, str | None]:
    if not paper.html_url:
        return {"html": None, "source_url": paper.source_url}
    raw = _fetch_url_text(paper.html_url)
    if raw is None:
        return {"html": None, "source_url": paper.source_url or paper.html_url}
    return {
        "html": prepare_arxiv_html_for_viewer(raw, paper.html_url),
        "source_url": paper.source_url or paper.html_url,
    }


def paper_html(paper: SQLAPaper) -> dict[str, str | None]:
    if paper.source_type == "arxiv":
        return _arxiv_paper_html(paper)
    return _default_paper_html(paper)


def counts_by_source_for_date(
    db: Session, source_types: set[str], run_date: date
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for source_type in sorted(source_types):
        if source_type not in KNOWN_SOURCE_TYPES:
            continue
        counts[source_type] = count_papers_for_source(db, source_type, run_date)
    return counts


def papers_for_sources(
    db: Session, source_types: set[str], run_date: date
) -> list[SQLAPaper]:
    papers: list[SQLAPaper] = []
    for source_type in sorted(source_types):
        if source_type not in KNOWN_SOURCE_TYPES:
            raise ValueError(f"Unknown source provider: {source_type}")
        papers.extend(papers_for_source(db, source_type, run_date))
    return papers


def ensure_default_data_sources(db: Session) -> list[SQLADataSource]:
    for source_type, defaults in DEFAULT_SOURCES.items():
        existing = db.query(SQLADataSource).filter(SQLADataSource.source_type == source_type).first()
        if existing:
            continue
        now = datetime.now(timezone.utc)
        db.add(
            SQLADataSource(
                source_type=source_type,
                name=defaults["name"],
                enabled=defaults["enabled"],
                settings=defaults["settings"],
                created_at=now,
                updated_at=now,
            )
        )
    db.flush()
    return list_data_sources(db)


def list_data_sources(db: Session) -> list[SQLADataSource]:
    sources = db.query(SQLADataSource).order_by(SQLADataSource.name.asc()).all()
    order = {"arxiv": 0, "lesswrong": 1}
    return sorted(sources, key=lambda source: order.get(source.source_type, 99))


def enabled_source_types(db: Session) -> set[str]:
    return {
        source.source_type
        for source in ensure_default_data_sources(db)
        if source.enabled
    }


def update_data_source(
    db: Session,
    source_type: str,
    *,
    enabled: bool | None = None,
    settings: dict | None = None,
) -> SQLADataSource:
    ensure_default_data_sources(db)
    source = db.query(SQLADataSource).filter(SQLADataSource.source_type == source_type).first()
    if not source:
        raise NotFound("Data source not found")

    if enabled is not None:
        source.enabled = enabled
    if settings is not None:
        source.settings = {**(source.settings or {}), **settings}
    source.updated_at = datetime.now(timezone.utc)
    db.flush()
    db.refresh(source)
    return source
