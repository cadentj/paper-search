"""Tests for daily index DB reads."""

from datetime import date, datetime, timezone

from app.models.paper import Paper
from app.services.daily_index_store import candidates_for_date, count_for_date


def test_candidates_for_date_reads_db(db_session):
    now = datetime.now(timezone.utc)
    paper = Paper(
        id="paper-1",
        source_type="arxiv",
        source_id="2605.01234",
        title="Shard",
        abstract="Body",
        search_text="Body",
        authors=[],
        categories=["cs.AI"],
        published_at=datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc),
        created_at=now,
        updated_at=now,
    )
    db_session.add(paper)
    db_session.commit()

    result = candidates_for_date(
        db_session, source_type="arxiv", run_date=date(2026, 5, 18)
    )
    assert len(result.papers) == 1
    assert result.papers[0].title == "Shard"
    assert result.papers[0].search_text == "Body"
    assert count_for_date(db_session, source_type="arxiv", run_date=date(2026, 5, 18)) == 1
