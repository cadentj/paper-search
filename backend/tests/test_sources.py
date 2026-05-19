"""Tests for daily source index reads."""

import uuid
from datetime import date, datetime, timezone

from app.models.paper import SQLAPaper
from app.services.sources import count_papers_for_source, papers_for_source


def test_papers_for_source_uses_injected_session(db_session):
    run_date = date(2026, 5, 1)
    paper = SQLAPaper(
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

    assert count_papers_for_source(db_session, "arxiv", run_date) == 1
    papers = papers_for_source(db_session, "arxiv", run_date)
    assert len(papers) == 1
    assert papers[0].source_id == "2605.00001"
