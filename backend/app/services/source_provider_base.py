"""Shared DB-backed provider behavior."""

from __future__ import annotations

import logging
from datetime import date

from app.db.session import SessionLocal
from app.models.paper import Paper
from app.services.daily_index_store import count_for_date, papers_for_date
from app.services.public_r2_index import http_get_text

logger = logging.getLogger(__name__)


class DbBackedSourceProvider:
    source_type: str

    def count_for_date(self, run_date: date) -> int:
        db = SessionLocal()
        try:
            return count_for_date(db, source_type=self.source_type, run_date=run_date)
        except Exception:
            logger.exception(
                "failed to read %s index count for %s", self.source_type, run_date
            )
            return 0
        finally:
            db.close()

    def papers_for_date(self, run_date: date) -> list[Paper]:
        db = SessionLocal()
        try:
            return papers_for_date(
                db, source_type=self.source_type, run_date=run_date
            )
        finally:
            db.close()

    def html_for_paper(self, paper: Paper) -> dict[str, str | None]:
        return {
            "html": http_get_text(paper.html_url) if paper.html_url else None,
            "source_url": paper.source_url,
        }
