"""Tests for loading shard items into papers."""

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

from paper_search_core.index_records import IndexSettings
from paper_search_core.models import Base, Paper
from paper_search_scripts.index_loader import _upsert_paper, load_arxiv_day, load_lesswrong_day


@pytest.fixture
def index_settings() -> IndexSettings:
    return IndexSettings(
        arxiv_html_public_base_url="https://example.com/arxiv/",
        lesswrong_html_public_base_url="https://example.com/lesswrong/",
    )


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


def test_load_arxiv_day_skips_empty_abstract(db_session, index_settings):
    total, searchable, skipped = load_arxiv_day(
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
        settings=index_settings,
    )
    db_session.commit()
    assert total == 2
    assert searchable == 1
    assert skipped == 0
    count = (
        db_session.query(Paper)
        .filter(
            Paper.source_type == "arxiv",
            func.date(Paper.published_at) == date(2026, 5, 18),
        )
        .count()
    )
    assert count == 1


def test_load_lesswrong_day_uses_excerpt_for_abstract(db_session, index_settings):
    total, searchable = load_lesswrong_day(
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
        ],
        settings=index_settings,
    )
    db_session.commit()
    assert total == 1
    assert searchable == 1
    paper = db_session.query(Paper).filter(Paper.source_id == "abc").one()
    assert paper.abstract == "hello world"
    assert paper.search_text == "hello world"
