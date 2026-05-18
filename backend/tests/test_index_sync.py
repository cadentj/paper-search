"""Tests for index record mapping and SQLite daily index store."""

from datetime import date, datetime, timezone

from app.services.daily_index_store import (
    candidates_for_date,
    count_for_date,
    upsert_arxiv_day,
    upsert_lesswrong_day,
)
from app.services.index_records import (
    arxiv_is_searchable,
    arxiv_record_from_shard,
)


class TestIndexRecords:
    def test_arxiv_record_from_shard(self):
        record = arxiv_record_from_shard(
            {
                "arxiv_id": "2605.01234",
                "title": "Indexed Title",
                "abstract": "Indexed abstract text.",
                "authors": ["Author One"],
                "categories": ["cs.AI"],
                "latest_version_date": "2026-05-16T18:00:00Z",
                "html_key": "data/2605/2605.01234.html",
            }
        )
        assert record["abstract"] == "Indexed abstract text."
        assert record["search_text"] == "Indexed abstract text."
        assert record["authors"] == ["Author One"]

    def test_arxiv_is_searchable(self):
        assert arxiv_is_searchable({"abstract": "x"})
        assert not arxiv_is_searchable({"abstract": " "})


class TestDailyIndexStore:
    def test_upsert_arxiv_day_skips_empty_abstract(self, db_session):
        total, searchable, skipped = upsert_arxiv_day(
            db_session,
            run_date=date(2026, 5, 18),
            shard_items=[
                {
                    "arxiv_id": "2605.01234",
                    "title": "Has abstract",
                    "abstract": "A",
                    "categories": ["cs.AI"],
                    "latest_version_date": "2026-05-18T12:00:00Z",
                },
                {
                    "arxiv_id": "2605.09999",
                    "title": "No abstract",
                    "abstract": "",
                    "categories": ["cs.AI"],
                },
            ],
        )
        db_session.commit()
        assert total == 2
        assert searchable == 1
        assert skipped == 0
        assert count_for_date(db_session, source_type="arxiv", run_date=date(2026, 5, 18)) == 1

    def test_upsert_lesswrong_day_skips_empty_preview(self, db_session):
        total, searchable = upsert_lesswrong_day(
            db_session,
            run_date=date(2026, 5, 18),
            shard_items=[
                {
                    "post_id": "abc",
                    "title": "T",
                    "text_preview": "hello world",
                    "posted_at": "2026-05-18T12:00:00Z",
                    "page_url": "https://www.lesswrong.com/posts/abc",
                },
                {
                    "post_id": "def",
                    "title": "No",
                    "text_preview": "",
                    "posted_at": "2026-05-18T13:00:00Z",
                    "page_url": "https://www.lesswrong.com/posts/def",
                },
            ],
        )
        db_session.commit()
        assert total == 2
        assert searchable == 1
        result = candidates_for_date(
            db_session, source_type="lesswrong", run_date=date(2026, 5, 18)
        )
        assert len(result.papers) == 1
        assert result.papers[0].source_id == "abc"

    def test_candidates_for_date_reads_db(self, db_session):
        record = arxiv_record_from_shard(
            {
                "arxiv_id": "2605.01234",
                "title": "Shard",
                "abstract": "Body",
                "categories": ["cs.AI"],
                "latest_version_date": "2026-05-18T12:00:00Z",
            }
        )
        from app.services.daily_index_store import _upsert_paper

        now = datetime.now(timezone.utc)
        _upsert_paper(db_session, record=record, now=now)
        db_session.commit()

        result = candidates_for_date(
            db_session, source_type="arxiv", run_date=date(2026, 5, 18)
        )
        assert result.papers[0].title == "Shard"
        assert result.papers[0].search_text == "Body"
