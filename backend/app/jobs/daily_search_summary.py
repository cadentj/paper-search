"""Daily search summary worker job."""

import logging
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.job import SQLAJob
from app.models.search_run import SQLASearchRun
from app.services import filters as filter_service
from app.llm.client import stream_structured_response
from app.llm.config import SUMMARY_PROFILE
from app.llm.prompts import SUMMARY_SYSTEM_PROMPT, SUMMARY_USER_PROMPT
from app.llm.schemas import SearchSummaryResponse
from app.llm.summary_stream import extract_complete_summary, extract_partial_summary
from paper_search_core.schemas.daily_search import PaperMatchPayload

logger = logging.getLogger(__name__)

SUMMARY_DRAFT_COMMIT_INTERVAL_SECONDS = 0.4
SUMMARY_DRAFT_MIN_CHAR_DELTA = 40
SUMMARY_DRAFT_MIN_CHARS = 120
SUMMARY_MIN_BODY_CHARS = 200


def _fallback_summary(db, run: SQLASearchRun) -> dict:
    active_filters = len(filter_service.list_filters(db, status="active"))
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


def _is_adequate_summary_body(summary_text: str, match_count: int) -> bool:
    if match_count <= 0:
        return True
    body = summary_text.strip()
    if len(body) < SUMMARY_MIN_BODY_CHARS:
        return False
    upper = body.upper()
    return "CLAIMS" in upper or "TOPICS" in upper


def _should_commit_summary_draft(
    *,
    partial_summary: str,
    last_committed_summary: str,
    last_commit_at: float,
    now: float,
) -> bool:
    if partial_summary == last_committed_summary:
        return False
    if not last_committed_summary:
        return True
    if now - last_commit_at >= SUMMARY_DRAFT_COMMIT_INTERVAL_SECONDS:
        return True
    return (
        len(partial_summary) - len(last_committed_summary)
        >= SUMMARY_DRAFT_MIN_CHAR_DELTA
    )


def run(db: Session, job: SQLAJob) -> None:
    """Summarize persisted matches for a daily search run."""
    from app.services import search_runs

    search_run_id = job.subject_id
    if not search_run_id:
        return

    try:
        run = db.query(SQLASearchRun).filter(SQLASearchRun.id == search_run_id).first()
        if not run:
            return

        search_runs.set_summary_status(db, run, job, status="running")

        match_payloads = search_runs.match_payloads_for_run(db, search_run_id)
        if match_payloads:
            matches_text = PaperMatchPayload.format_grouped_for_summary(match_payloads)
            user_prompt = SUMMARY_USER_PROMPT.format(matches_text=matches_text)
            text_buffer = ""
            last_committed_summary = ""
            last_commit_at = 0.0

            def handle_delta(delta: str) -> None:
                nonlocal text_buffer, last_committed_summary, last_commit_at
                text_buffer += delta
                partial_summary = extract_partial_summary(text_buffer)
                if (
                    partial_summary is None
                    or len(partial_summary.strip()) < SUMMARY_DRAFT_MIN_CHARS
                ):
                    return

                now = time.monotonic()
                if not _should_commit_summary_draft(
                    partial_summary=partial_summary,
                    last_committed_summary=last_committed_summary,
                    last_commit_at=last_commit_at,
                    now=now,
                ):
                    return

                search_runs.update_summary_draft(db, run, partial_summary)
                last_committed_summary = partial_summary
                last_commit_at = now

            result = stream_structured_response(
                system_prompt=SUMMARY_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                response_model=SearchSummaryResponse,
                on_text_delta=handle_delta,
                profile=SUMMARY_PROFILE,
            )
            summary_data = dict(result["content"])
            summary_text = (summary_data.get("summary") or "").strip()
            if not summary_text and text_buffer.strip():
                summary_text = (
                    extract_complete_summary(text_buffer)
                    or extract_partial_summary(text_buffer)
                    or ""
                ).strip()
            if not summary_text and (run.summary or "").strip():
                summary_text = run.summary.strip()
            if not _is_adequate_summary_body(summary_text, len(match_payloads)):
                logger.warning(
                    "daily_search_summary run=%s inadequate summary "
                    "(len=%d, buffer_len=%d, citations=%d, preview=%r)",
                    search_run_id,
                    len(summary_text),
                    len(text_buffer),
                    len(summary_data.get("citations") or []),
                    summary_text[:120],
                )
                raise RuntimeError(
                    "Daily summary generation returned an empty or placeholder digest. "
                    "Try running daily search again."
                )
        else:
            summary_data = _fallback_summary(db, run)
            summary_text = (summary_data.get("summary") or "").strip()

        search_runs.complete_summary(
            db,
            run,
            job,
            summary=summary_text,
            citations=summary_data.get("citations", []),
        )

    except Exception as e:
        db.rollback()
        run = db.query(SQLASearchRun).filter(SQLASearchRun.id == search_run_id).first()
        if run:
            run.error = str(e)
            run.completed_at = datetime.now(timezone.utc)
            search_runs.set_summary_status(
                db, run, job, status="failed", error=run.error
            )
        logger.exception("daily_search_summary run=%s failed", search_run_id)
        raise
