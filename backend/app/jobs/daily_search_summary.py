"""Daily search summary worker job."""

import logging
from datetime import datetime, timezone

from app.db.session import SessionLocal
from app.models.filter import Filter
from app.models.paper import Paper
from app.models.paper_match import PaperMatch
from app.models.search_run import SearchRun
from app.models.job import Job
from app.services.jobs import get_or_create_job_for_subject, set_job_status
from app.llm.client import call_llm
from app.llm.config import SUMMARY_PROFILE
from app.llm.prompts import SUMMARY_SYSTEM_PROMPT, SUMMARY_USER_PROMPT
from app.llm.schemas import SearchSummaryResponse
from paper_search_core.schemas.daily_search import PaperMatchPayload

logger = logging.getLogger(__name__)


def _match_payloads_for_run(db, search_run_id: str) -> list[PaperMatchPayload]:
    rows = (
        db.query(PaperMatch, Paper, Filter)
        .join(Paper, PaperMatch.paper_id == Paper.id)
        .join(Filter, PaperMatch.filter_id == Filter.id)
        .filter(PaperMatch.search_run_id == search_run_id)
        .order_by(PaperMatch.created_at.asc(), PaperMatch.id.asc())
        .all()
    )
    return [
        PaperMatchPayload(
            match_id=match.id,
            paper=paper.to_search_payload(),
            filter_name=filter.name,
            result=match.result or "",
        )
        for match, paper, filter in rows
    ]


def _fallback_summary(db, run: SearchRun) -> dict:
    active_filters = db.query(Filter).filter(Filter.status == "active").count()
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


def _set_run_status(
    db,
    run: SearchRun,
    job: Job,
    *,
    status: str,
    error: str | None = None,
) -> None:
    run.status = status
    if error is not None:
        run.error = error
    set_job_status(job, status=status, error=error)
    db.commit()


def _resolve_summary_job(db, search_run_id: str, job_id: str | None) -> Job:
    if job_id:
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            return job
    return get_or_create_job_for_subject(
        db,
        kind="daily_search_summary",
        subject_type="search_run",
        subject_id=search_run_id,
    )


def summarize_daily_search(search_run_id: str, job_id: str | None = None) -> None:
    """Worker job: summarize persisted matches for a daily search run."""
    db = SessionLocal()
    try:
        run = db.query(SearchRun).filter(SearchRun.id == search_run_id).first()
        if not run:
            return
        job = _resolve_summary_job(db, search_run_id, job_id)
        set_job_status(job, status="running")
        db.commit()

        match_payloads = _match_payloads_for_run(db, search_run_id)
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

        run.summary = summary_data.get("summary", "")
        run.summary_citations = summary_data.get("citations", [])
        run.completed_at = datetime.now(timezone.utc)
        _set_run_status(db, run, job, status="completed")

    except Exception as e:
        db.rollback()
        run = db.query(SearchRun).filter(SearchRun.id == search_run_id).first()
        if run:
            run.status = "failed"
            run.error = str(e)
            run.completed_at = datetime.now(timezone.utc)
            job = _resolve_summary_job(db, search_run_id, job_id)
            _set_run_status(db, run, job, status="failed", error=run.error)
        logger.exception("daily_search_summary run=%s failed", search_run_id)
        raise
    finally:
        db.close()
