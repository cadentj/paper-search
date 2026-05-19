"""Daily search summary worker job."""

import logging
from datetime import datetime, timezone

from app.db.session import database
from app.models.search_run import SQLASearchRun
from app.services import filters as filter_service
from app.models.job import SQLAJob
from app.llm.client import call_llm
from app.llm.config import SUMMARY_PROFILE
from app.llm.prompts import SUMMARY_SYSTEM_PROMPT, SUMMARY_USER_PROMPT
from app.llm.schemas import SearchSummaryResponse

logger = logging.getLogger(__name__)


def _fallback_summary(db, run: SQLASearchRun) -> dict:
    active_filters = len(filter_service.list_active_filters(db))
    if active_filters == 0:
        return {"summary": "No active filters to search.", "citations": []}
    if not run.candidate_count:
        return {
            "summary": "No items were available for this daily search.",
            "citations": [],
        }
    return {
        "summary": "No relevant items found in today's search.",
        "citations": [],
    }


def summarize_daily_search(search_run_id: str, job_id: str | None = None) -> None:
    """Worker job: summarize persisted matches for a daily search run."""
    from app.services import search_runs

    with database.session() as db:
        try:
            run = db.query(SQLASearchRun).filter(SQLASearchRun.id == search_run_id).first()
            if not run:
                return
            job = search_runs.resolve_summary_job(db, search_run_id, job_id)
            search_runs.set_summary_status(db, run, job, status="running")

            match_payloads = search_runs.match_payloads_for_run(db, search_run_id)
            if match_payloads:
                matches_text = "\n---\n".join(p.model_dump_json() for p in match_payloads)
                user_prompt = SUMMARY_USER_PROMPT.format(matches_text=matches_text)
                result = call_llm(
                    system_prompt=SUMMARY_SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    response_model=SearchSummaryResponse,
                    profile=SUMMARY_PROFILE,
                )
                summary_data = result["content"]
            else:
                summary_data = _fallback_summary(db, run)

            search_runs.complete_summary(
                db,
                run,
                job,
                summary=summary_data.get("summary", ""),
                citations=summary_data.get("citations", []),
            )

        except Exception as e:
            db.rollback()
            run = db.query(SQLASearchRun).filter(SQLASearchRun.id == search_run_id).first()
            if run:
                run.error = str(e)
                run.completed_at = datetime.now(timezone.utc)
                job = search_runs.resolve_summary_job(db, search_run_id, job_id)
                search_runs.set_summary_status(db, run, job, status="failed", error=run.error)
            logger.exception("daily_search_summary run=%s failed", search_run_id)
            raise
