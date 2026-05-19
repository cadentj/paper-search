"""Daily search sources: index reads and paper HTML."""

from __future__ import annotations

import logging
from datetime import date

import httpx
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.services import settings as settings_service
from paper_search_core.models.paper import SQLAPaper
from app.utils.html_parser import prepare_arxiv_html_for_viewer

logger = logging.getLogger(__name__)

KNOWN_SOURCE_TYPES = frozenset(settings_service.SOURCE_CATALOG)


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
        counts_for_source = (
            db.query(SQLAPaper)
            .filter(
                SQLAPaper.source_type == source_type,
                func.date(SQLAPaper.published_at) == run_date,
            )
            .count()
        )
        counts[source_type] = counts_for_source
    return counts


def papers_for_sources(
    db: Session, source_types: set[str], run_date: date
) -> list[SQLAPaper]:
    papers: list[SQLAPaper] = []
    for source_type in sorted(source_types):
        if source_type not in KNOWN_SOURCE_TYPES:
            raise ValueError(f"Unknown source provider: {source_type}")
        papers_for_source = (
            db.query(SQLAPaper)
            .filter(
                SQLAPaper.source_type == source_type,
                func.date(SQLAPaper.published_at) == run_date,
            )
            .all()
        )
        papers.extend(papers_for_source)
    return papers


def enabled_source_types(db: Session) -> set[str]:
    return settings_service.enabled_source_types(db)
