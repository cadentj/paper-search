"""LessWrong source — SQLite daily index and R2 HTML access."""

from __future__ import annotations

import logging
from datetime import date

from app.db.session import SessionLocal
from app.models.paper import Paper
from app.services.daily_index_store import candidates_for_date, rollup_count
from app.services.index_records import lesswrong_public_url
from app.services.public_r2_index import http_get_text
from app.services.source_types import SourceFetchResult

logger = logging.getLogger(__name__)


def fetch_public_post_html(*, html_url: str | None = None, html_key: str | None = None) -> str | None:
    url = html_url or (public_url(html_key) if html_key else None)
    if not url:
        return None
    return http_get_text(url)


def public_url(path_or_key: str) -> str:
    return lesswrong_public_url(path_or_key)


class LessWrongProvider:
    source_type = "lesswrong"

    def count_for_date(self, run_date: date) -> int:
        db = SessionLocal()
        try:
            return rollup_count(db, source_type=self.source_type, run_date=run_date)
        except Exception:
            logger.exception("failed to read LessWrong index count for %s", run_date)
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
            logger.exception("failed to read LessWrong candidates for %s", run_date)
            return SourceFetchResult(
                items=[],
                errors=[f"LessWrong fetch failed: {exc}"],
            )
        finally:
            db.close()

    def html_for_paper(self, paper: Paper) -> dict[str, str | None]:
        try:
            html = fetch_public_post_html(
                html_url=paper.html_url,
                html_key=(paper.source_metadata or {}).get("html_key"),
            )
        except Exception:
            logger.exception("failed to fetch LessWrong HTML for paper=%s", paper.id)
            html = None
        return {
            "html": html,
            "source_url": paper.source_url or paper.landing_url,
        }
