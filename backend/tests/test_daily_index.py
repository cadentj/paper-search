"""Tests for daily index DB reads."""

from datetime import date, datetime, timezone

from app.models.paper import Paper
from app.services.daily_index_store import count_for_date, papers_for_date


def test_papers_for_date_reads_db(db_session):
    now = datetime.now(timezone.utc)
    paper = Paper(
        id="paper-1",
        source_type="arxiv",
        source_id="2605.01234",
        title="Shard",
        search_text="Body",
        authors=[],
        published_at=datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc),
        created_at=now,
    )
    db_session.add(paper)
    db_session.commit()

    papers = papers_for_date(
        db_session, source_type="arxiv", run_date=date(2026, 5, 18)
    )
    assert len(papers) == 1
    assert papers[0].title == "Shard"
    assert papers[0].search_text == "Body"
    assert count_for_date(db_session, source_type="arxiv", run_date=date(2026, 5, 18)) == 1
