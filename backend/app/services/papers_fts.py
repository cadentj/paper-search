"""SQLite FTS5 index and daily-search candidate selection."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.models.filter import FilterPayload
from paper_search_core.models.paper import SQLAPaper
from paper_search_core.schemas.daily_search import PaperPayload

FTS_MAX_CANDIDATES_PER_FILTER = 25
FTS_MIN_CANDIDATES_PER_FILTER = 3
FTS_RELATIVE_SCORE_CUTOFF = 0.20

_FTS5_SPECIAL = re.compile(r'["()*]')
_TOKEN = re.compile(r"[a-z0-9]{2,}", re.IGNORECASE)

_CREATE_PAPERS_FTS = text(
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS papers_fts USING fts5(
        paper_id UNINDEXED,
        title,
        search_text,
        authors,
        source_id,
        tokenize='porter unicode61'
    )
    """
)

_INSERT_PAPER = text(
    """
    INSERT INTO papers_fts (paper_id, title, search_text, authors, source_id)
    VALUES (:paper_id, :title, :search_text, :authors, :source_id)
    """
)

_SEARCH_CANDIDATES = text(
    """
    SELECT papers_fts.paper_id, bm25(papers_fts) AS bm25_score
    FROM papers_fts
    JOIN papers p ON p.id = papers_fts.paper_id
    WHERE papers_fts MATCH :query
      AND date(p.published_at) = :run_date
    ORDER BY bm25_score ASC
    LIMIT :fetch_limit
    """
)

_BACKFILL_PAPERS = text(
    """
    INSERT INTO papers_fts (paper_id, title, search_text, authors, source_id)
    SELECT
        id,
        title,
        search_text,
        COALESCE(
            (
                SELECT group_concat(value, ', ')
                FROM json_each(papers.authors)
            ),
            ''
        ),
        COALESCE(source_id, '')
    FROM papers
    WHERE id NOT IN (SELECT paper_id FROM papers_fts)
    """
)


@dataclass(frozen=True)
class FtsCandidate:
    paper_id: str
    bm25_score: float


def ensure_papers_fts(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(_CREATE_PAPERS_FTS)


def _authors_text(authors: list | None) -> str:
    if not authors:
        return ""
    return ", ".join(str(a) for a in authors)


def index_paper(db: Session, paper: SQLAPaper) -> None:
    db.execute(
        _INSERT_PAPER,
        {
            "paper_id": paper.id,
            "title": paper.title or "",
            "search_text": paper.search_text or "",
            "authors": _authors_text(paper.authors),
            "source_id": paper.source_id or "",
        },
    )


def rebuild_papers_fts(db: Session) -> None:
    paper_count = db.execute(text("SELECT COUNT(*) FROM papers")).scalar_one()
    fts_count = db.execute(text("SELECT COUNT(*) FROM papers_fts")).scalar_one()
    if paper_count and fts_count == 0:
        db.execute(_BACKFILL_PAPERS)


def _escape_fts5_term(term: str) -> str:
    return _FTS5_SPECIAL.sub("", term)


def _tokenize_filter_text(text_value: str) -> list[str]:
    return [t.lower() for t in _TOKEN.findall(text_value)]


def build_filter_fts_query(filter: FilterPayload) -> str | None:
    definition = filter.definition or {}
    parts = [filter.name, definition.get("description", "")]
    tokens: list[str] = []
    seen: set[str] = set()
    for part in parts:
        for token in _tokenize_filter_text(part or ""):
            if token not in seen:
                seen.add(token)
                tokens.append(_escape_fts5_term(token))
    if not tokens:
        return None
    return " OR ".join(tokens)


def apply_relevance_cutoff(candidates: list[FtsCandidate]) -> list[FtsCandidate]:
    if not candidates:
        return []

    scored: list[tuple[FtsCandidate, float]] = [
        (candidate, -candidate.bm25_score) for candidate in candidates
    ]
    best_relevance = max(relevance for _, relevance in scored)
    threshold = FTS_RELATIVE_SCORE_CUTOFF * best_relevance

    kept: list[FtsCandidate] = []
    for index, (candidate, relevance) in enumerate(scored):
        if index < FTS_MIN_CANDIDATES_PER_FILTER:
            kept.append(candidate)
        elif relevance >= threshold:
            kept.append(candidate)
        if len(kept) >= FTS_MAX_CANDIDATES_PER_FILTER:
            break
    return kept


def search_filter_candidates(
    db: Session,
    *,
    filter: FilterPayload,
    run_date: date,
) -> list[FtsCandidate]:
    query = build_filter_fts_query(filter)
    if query is None:
        return []

    rows = db.execute(
        _SEARCH_CANDIDATES,
        {
            "query": query,
            "run_date": run_date.isoformat(),
            "fetch_limit": FTS_MAX_CANDIDATES_PER_FILTER,
        },
    ).all()
    return [
        FtsCandidate(paper_id=row.paper_id, bm25_score=float(row.bm25_score))
        for row in rows
    ]


def select_daily_search_pairs(
    db: Session,
    *,
    filters: list[FilterPayload],
    papers_by_id: dict[str, PaperPayload],
    run_date: date,
) -> list[tuple[FilterPayload, PaperPayload]]:
    pairs: list[tuple[FilterPayload, PaperPayload]] = []
    for filter in filters:
        candidates = search_filter_candidates(db, filter=filter, run_date=run_date)
        for candidate in apply_relevance_cutoff(candidates):
            paper = papers_by_id.get(candidate.paper_id)
            if paper is not None:
                pairs.append((filter, paper))
    return pairs
