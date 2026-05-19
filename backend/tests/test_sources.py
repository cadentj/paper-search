"""Tests for daily source index reads."""

import uuid
from datetime import date, datetime, timezone

from paper_search_core.models.paper import SQLAPaper
from app.services.sources import (
    counts_by_source_for_date,
    paper_html,
    papers_for_sources,
)


def test_papers_for_sources_uses_injected_session(db_session):
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

    assert counts_by_source_for_date(db_session, {"arxiv"}, run_date) == {"arxiv": 1}
    papers = papers_for_sources(db_session, {"arxiv"}, run_date)
    assert len(papers) == 1
    assert papers[0].source_id == "2605.00001"


def test_arxiv_paper_html_uses_r2_for_fetch_and_arxiv_for_assets(monkeypatch):
    fetched_urls = []

    class FakeResponse:
        text = """
        <html>
        <head>
            <base href="https://r2.example/data/2012/2012.14425.html">
            <link rel="stylesheet" href="/static/browse/0.3.4/css/arxiv-html-papers.css">
        </head>
        <body>
            <header class="arxiv-html-header">arXiv header</header>
            <p id="para1">This paragraph has enough text to become addressable.</p>
        </body>
        </html>
        """

        def raise_for_status(self):
            return None

    def fake_get(url, **kwargs):
        fetched_urls.append(url)
        return FakeResponse()

    monkeypatch.setattr("app.services.sources.httpx.get", fake_get)
    paper = SQLAPaper(
        id=str(uuid.uuid4()),
        source_type="arxiv",
        source_id="2012.14425",
        title="Test Paper",
        search_text="abstract",
        authors=["Author"],
        html_url="https://r2.example/data/2012/2012.14425.html",
        source_url="https://arxiv.org/abs/2012.14425",
        created_at=datetime.now(timezone.utc),
    )

    result = paper_html(paper)

    assert fetched_urls == ["https://r2.example/data/2012/2012.14425.html"]
    assert result["source_url"] == "https://arxiv.org/abs/2012.14425"
    assert '<base href="https://arxiv.org/html/2012.14425"/>' in result["html"]
    assert "arxiv-html-header" not in result["html"]
