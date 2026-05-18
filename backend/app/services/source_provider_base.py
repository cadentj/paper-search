"""Shared DB-backed provider behavior."""

from __future__ import annotations

import logging
from datetime import date

from app.db.session import SessionLocal
from app.models.paper import Paper
from app.services.daily_index_store import candidates_for_date, rollup_count
from app.services.public_r2_index import http_get_text
from app.services.source_types import SourceFetchResult

logger = logging.getLogger(__name__)


class DbBackedSourceProvider:
    source_type: str

    def count_for_date(self, run_date: date) -> int:
        db = SessionLocal()
        try:
            return rollup_count(db, source_type=self.source_type, run_date=run_date)
        except Exception:
            logger.exception(
                "failed to read %s index count for %s", self.source_type, run_date
            )
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
            logger.exception(
                "failed to read %s candidates for %s", self.source_type, run_date
            )
            return SourceFetchResult(
                items=[],
                errors=[f"{self.source_type} fetch failed: {exc}"],
            )
        finally:
            db.close()

    def html_for_paper(self, paper: Paper) -> dict[str, str | None]:
        return {
            "html": http_get_text(paper.html_url) if paper.html_url else None,
            "source_url": paper.source_url,
        }
