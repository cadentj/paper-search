"""arXiv source — SQLite daily index and R2 HTML access."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from app.db.session import SessionLocal
from app.models.paper import Paper
from app.services.daily_index_store import candidates_for_date, rollup_count
from app.services.html_parser import prepare_arxiv_html_for_viewer
from app.services.index_records import arxiv_public_url, normalize_arxiv_id
from app.services.public_r2_index import http_get_text
from app.services.source_types import SourceFetchResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PaperHtmlDocument:
    arxiv_id: str
    source_url: str
    html: str


def fetch_public_paper_html(
    *,
    arxiv_id: str | None = None,
    html_url: str | None = None,
) -> dict[str, str] | None:
    url = html_url
    if not url and arxiv_id:
        from app.services.index_records import arxiv_html_key_for_id

        url = public_url(arxiv_html_key_for_id(normalize_arxiv_id(arxiv_id)))
    if not url:
        return None

    text = http_get_text(url)
    if text is None:
        return None
    return {"html": text, "source_url": url}


def public_url(path_or_key: str) -> str:
    return arxiv_public_url(path_or_key)


def arxiv_html_url(arxiv_id: str) -> str:
    return f"https://arxiv.org/html/{normalize_arxiv_id(arxiv_id)}"


def read_paper_html(
    arxiv_id: str | None,
    *,
    html_url: str | None = None,
) -> PaperHtmlDocument | None:
    remote_html = fetch_public_paper_html(arxiv_id=arxiv_id, html_url=html_url)
    if not remote_html:
        return None

    return PaperHtmlDocument(
        arxiv_id=normalize_arxiv_id(arxiv_id or ""),
        source_url=remote_html["source_url"],
        html=remote_html["html"],
    )


class ArxivProvider:
    source_type = "arxiv"

    def count_for_date(self, run_date: date) -> int:
        db = SessionLocal()
        try:
            return rollup_count(db, source_type=self.source_type, run_date=run_date)
        except Exception:
            logger.exception("failed to read arXiv index count for %s", run_date)
            return 0
        finally:
            db.close()

    def candidates_for_date(self, run_date: date) -> SourceFetchResult:
        db = SessionLocal()
        try:
            return candidates_for_date(
                db, source_type=self.source_type, run_date=run_date
            )
        except Exception as exc:
            logger.exception("failed to read arXiv candidates for %s", run_date)
            return SourceFetchResult(items=[], errors=[f"arXiv fetch failed: {exc}"])
        finally:
            db.close()

    def html_for_paper(self, paper: Paper) -> dict[str, str | None]:
        paper_html = read_paper_html(paper.arxiv_id, html_url=paper.html_url)
        if paper_html:
            return {
                "html": prepare_arxiv_html_for_viewer(
                    paper_html.html,
                    paper_html.source_url,
                ),
                "source_url": paper_html.source_url,
            }
        return {
            "html": None,
            "source_url": arxiv_html_url(paper.arxiv_id) if paper.arxiv_id else None,
        }
