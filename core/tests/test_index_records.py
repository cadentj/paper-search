"""Tests for shard → paper record mapping."""

import pytest

from paper_search_core.index_records import (
    IndexSettings,
    arxiv_is_searchable,
    arxiv_record_from_shard,
)


@pytest.fixture
def index_settings() -> IndexSettings:
    return IndexSettings(
        arxiv_html_public_base_url="https://example.com/arxiv/",
        lesswrong_html_public_base_url="https://example.com/lesswrong/",
    )


def test_arxiv_record_from_shard(index_settings: IndexSettings):
    record = arxiv_record_from_shard(
        {
            "arxiv_id": "2605.01234",
            "title": "Indexed Title",
            "abstract": "Indexed abstract text.",
            "authors": ["Author One"],
            "categories": ["cs.AI"],
            "latest_version_date": "2026-05-16T18:00:00Z",
            "html_key": "data/2605/2605.01234.html",
        },
        index_settings,
    )
    assert record["abstract"] == "Indexed abstract text."
    assert record["search_text"] == "Indexed abstract text."
    assert record["authors"] == ["Author One"]


def test_arxiv_is_searchable():
    assert arxiv_is_searchable({"abstract": "x"})
    assert not arxiv_is_searchable({"abstract": " "})
