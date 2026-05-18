"""arXiv source — SQLite daily index and R2 HTML access."""

from __future__ import annotations

from app.models.paper import Paper
from app.services.html_parser import prepare_arxiv_html_for_viewer
from app.services.public_r2_index import http_get_text
from app.services.source_provider_base import DbBackedSourceProvider


class ArxivProvider(DbBackedSourceProvider):
    source_type = "arxiv"

    def html_for_paper(self, paper: Paper) -> dict[str, str | None]:
        if not paper.html_url:
            return {"html": None, "source_url": paper.source_url}
        raw = http_get_text(paper.html_url)
        if raw is None:
            return {"html": None, "source_url": paper.source_url or paper.html_url}
        return {
            "html": prepare_arxiv_html_for_viewer(raw, paper.html_url),
            "source_url": paper.source_url or paper.html_url,
        }
