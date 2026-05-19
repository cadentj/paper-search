"""Tests for DB-backed source providers with caller-owned sessions."""

import uuid
from datetime import date, datetime, timezone

from app.services.arxiv_provider import ArxivProvider
from app.services.daily_index_store import count_for_date, papers_for_date
from app.models.paper import Paper


def test_arxiv_provider_uses_injected_session(db_session):
    run_date = date(2026, 5, 1)
    paper = Paper(
        id=str(uuid.uuid4()),
        source_type="arxiv",
        source_id="2605.00001",
        title="Test Paper",
        search_text="abstract",
        authors=["Author"],
        published_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(paper)
    db_session.commit()

    provider = ArxivProvider()
    assert provider.count_for_date(db_session, run_date) == 1
    papers = provider.papers_for_date(db_session, run_date)
    assert len(papers) == 1
    assert papers[0].source_id == "2605.00001"

    assert count_for_date(db_session, source_type="arxiv", run_date=run_date) == 1
    assert len(papers_for_date(db_session, source_type="arxiv", run_date=run_date)) == 1
