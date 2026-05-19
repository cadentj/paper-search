"""Unit tests for SQLite FTS5 daily-search candidate selection."""

import uuid
from datetime import date, datetime, time, timezone

import pytest

from app.models.filter import FilterPayload
from app.services.papers_fts import (
    FTS_MAX_CANDIDATES_PER_FILTER,
    FTS_MIN_CANDIDATES_PER_FILTER,
    FTS_RELATIVE_SCORE_CUTOFF,
    FtsCandidate,
    apply_relevance_cutoff,
    index_paper,
    search_filter_candidates,
    select_daily_search_pairs,
)
from paper_search_core.models.paper import SQLAPaper

def _run_date() -> date:
    return date(2026, 5, 19)


def _published_at(run_date: date) -> datetime:
    return datetime.combine(run_date, time.min, tzinfo=timezone.utc)


def _insert_paper(
    db_session,
    *,
    title: str,
    search_text: str,
    run_date: date | None = None,
    paper_id: str | None = None,
) -> SQLAPaper:
    run_date = run_date or _run_date()
    paper = SQLAPaper(
        id=paper_id or str(uuid.uuid4()),
        source_type="arxiv",
        source_id=str(uuid.uuid4())[:12],
        title=title,
        search_text=search_text,
        authors=["Test Author"],
        published_at=_published_at(run_date),
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(paper)
    db_session.flush()
    index_paper(db_session, paper)
    return paper


def _filter(filter_id: str, name: str, description: str) -> FilterPayload:
    return FilterPayload(
        id=filter_id,
        name=name,
        definition={"description": description},
    )


class TestApplyRelevanceCutoff:
    def test_empty_returns_empty(self):
        assert apply_relevance_cutoff([]) == []

    def test_keeps_top_three_even_when_weak(self):
        candidates = [
            FtsCandidate(paper_id="a", bm25_score=-10.0),
            FtsCandidate(paper_id="b", bm25_score=-5.0),
            FtsCandidate(paper_id="c", bm25_score=-1.0),
            FtsCandidate(paper_id="d", bm25_score=0.0),
        ]
        kept = apply_relevance_cutoff(candidates)
        assert [c.paper_id for c in kept] == ["a", "b", "c"]

    def test_drops_weak_tail_beyond_top_three(self):
        best = 10.0
        threshold = FTS_RELATIVE_SCORE_CUTOFF * best
        candidates = [
            FtsCandidate(paper_id="strong", bm25_score=-best),
            FtsCandidate(paper_id="mid", bm25_score=-(threshold + 0.5)),
            FtsCandidate(paper_id="weak2", bm25_score=-1.0),
            FtsCandidate(paper_id="weak3", bm25_score=-0.5),
            FtsCandidate(paper_id="weak4", bm25_score=0.0),
        ]
        kept = apply_relevance_cutoff(candidates)
        assert [c.paper_id for c in kept[:3]] == ["strong", "mid", "weak2"]
        assert "weak4" not in {c.paper_id for c in kept}


class TestFtsSearch:
    def test_fts_ranking_limits_per_filter(self, db_session):
        run_date = _run_date()
        filter_payload = _filter("f1", "quantum gravity", "quantum gravity unification")

        for index in range(30):
            _insert_paper(
                db_session,
                title=f"Paper {index}",
                search_text=(
                    "quantum gravity unification theory "
                    if index < 5
                    else f"unrelated topic filler {index}"
                ),
                run_date=run_date,
            )
        db_session.commit()

        raw = search_filter_candidates(
            db_session, filter=filter_payload, run_date=run_date
        )
        assert len(raw) <= FTS_MAX_CANDIDATES_PER_FILTER
        assert len(raw) > 0

        kept = apply_relevance_cutoff(raw)
        assert len(kept) <= FTS_MAX_CANDIDATES_PER_FILTER
        assert len(kept) >= FTS_MIN_CANDIDATES_PER_FILTER

    def test_weak_tail_cutoff(self, db_session):
        run_date = _run_date()
        filter_payload = _filter(
            "f1",
            "neural scaling",
            "neural network scaling laws",
        )

        for index in range(25):
            if index < 4:
                text = (
                    "neural network scaling laws describe power-law "
                    "behavior in large models"
                )
            else:
                text = f"network mention only filler document {index}"
            _insert_paper(
                db_session,
                title=f"Scaling paper {index}",
                search_text=text,
                run_date=run_date,
            )
        db_session.commit()

        raw = search_filter_candidates(
            db_session, filter=filter_payload, run_date=run_date
        )
        assert len(raw) == FTS_MAX_CANDIDATES_PER_FILTER

        kept = apply_relevance_cutoff(raw)
        assert FTS_MIN_CANDIDATES_PER_FILTER <= len(kept) < len(raw)

    def test_per_filter_different_subsets(self, db_session):
        run_date = _run_date()
        quantum_filter = _filter("q", "quantum", "quantum entanglement physics")
        scaling_filter = _filter("s", "scaling", "neural network scaling laws")

        quantum_paper = _insert_paper(
            db_session,
            title="Quantum entanglement survey",
            search_text="quantum entanglement and bell inequalities",
            run_date=run_date,
            paper_id="paper-quantum",
        )
        scaling_paper = _insert_paper(
            db_session,
            title="Neural scaling laws",
            search_text="neural network scaling laws in language models",
            run_date=run_date,
            paper_id="paper-scaling",
        )
        overlap_paper = _insert_paper(
            db_session,
            title="Quantum scaling crossover",
            search_text="quantum scaling crossover neural quantum models",
            run_date=run_date,
            paper_id="paper-overlap",
        )
        db_session.commit()

        papers_by_id = {
            quantum_paper.id: quantum_paper.to_search_payload(),
            scaling_paper.id: scaling_paper.to_search_payload(),
            overlap_paper.id: overlap_paper.to_search_payload(),
        }

        pairs = select_daily_search_pairs(
            db_session,
            filters=[quantum_filter, scaling_filter],
            papers_by_id=papers_by_id,
            run_date=run_date,
        )
        quantum_ids = {
            paper.id for filt, paper in pairs if filt.id == "q"
        }
        scaling_ids = {
            paper.id for filt, paper in pairs if filt.id == "s"
        }

        assert "paper-quantum" in quantum_ids
        assert "paper-scaling" not in quantum_ids
        assert "paper-scaling" in scaling_ids
        assert "paper-quantum" not in scaling_ids
        assert "paper-overlap" in quantum_ids & scaling_ids
