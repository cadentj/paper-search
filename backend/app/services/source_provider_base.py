"""Shared DB-backed provider behavior."""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy.orm import Session

from app.models.paper import Paper
from app.services.daily_index_store import count_for_date, papers_for_date
from app.services.public_r2_index import http_get_text

logger = logging.getLogger(__name__)


class DbBackedSourceProvider:
    source_type: str

    def count_for_date(self, db: Session, run_date: date) -> int:
        try:
            return count_for_date(db, source_type=self.source_type, run_date=run_date)
        except Exception:
            logger.exception(
                "failed to read %s index count for %s", self.source_type, run_date
            )
            return 0

    def papers_for_date(self, db: Session, run_date: date) -> list[Paper]:
        return papers_for_date(db, source_type=self.source_type, run_date=run_date)

    def html_for_paper(self, paper: Paper) -> dict[str, str | None]:
        return {
            "html": http_get_text(paper.html_url) if paper.html_url else None,
            "source_url": paper.source_url,
        }
