from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.jobs.daily_search import run_daily_search
from app.jobs.daily_search_summary import summarize_daily_search
from app.jobs.queues import enqueue_for_job
from app.models.filter import SQLAFilter
from app.models.job import SQLAJob
from paper_search_core.models.paper import SQLAPaper
from app.models.paper_match import PaperMatch, SQLAPaperMatch
from app.models.search_run import SQLASearchRun, SearchRun
from paper_search_core.daily_dates import DEFAULT_DAILY_SEARCH_DATE
from app.services.errors import Conflict, NotFound, ValidationFailed
from app.services.job_enqueue import commit_entities, enqueue_job, persist_then_enqueue
from app.services.jobs import get_or_create_job_for_subject
from app.services.jobs import create_job, latest_job_for_subject, set_job_status
from app.services.sources import enabled_source_types

ACTIVE_SUMMARY_JOB_STATUSES = {"queued", "running"}


def get_search_run(db: Session, search_run_id: str) -> SQLASearchRun:
    run = db.query(SQLASearchRun).filter(SQLASearchRun.id == search_run_id).first()
    if not run:
        raise NotFound("Search run not found")
    return run


def list_search_runs(db: Session) -> list[SQLASearchRun]:
    return db.query(SQLASearchRun).order_by(SQLASearchRun.created_at.desc()).all()


def latest_search_run(db: Session) -> SQLASearchRun | None:
    return db.query(SQLASearchRun).order_by(SQLASearchRun.created_at.desc()).first()


def search_run_payload(db: Session, run: SQLASearchRun) -> SearchRun:
    search_job = latest_job_for_subject(
        db,
        subject_type="search_run",
        subject_id=run.id,
        kind="daily_search",
    )
    return run.to_pydantic(job_id=search_job.id if search_job else None)


def summary_payload(run: SQLASearchRun):
    from app.api.search import DailySearchSummary, SummaryCitation

    if not run.summary:
        return None
    citations = [
        SummaryCitation.model_validate(c) for c in (run.summary_citations or [])
    ]
    return DailySearchSummary(
        search_run_id=run.id,
        summary=run.summary,
        citations=citations,
    )


def list_matches_for_run(db: Session, search_run_id: str) -> list[PaperMatch]:
    get_search_run(db, search_run_id)
    matches = (
        db.query(SQLAPaperMatch)
        .filter(SQLAPaperMatch.search_run_id == search_run_id)
        .all()
    )
    result = []
    for match in matches:
        paper = db.query(SQLAPaper).filter(SQLAPaper.id == match.paper_id).first()
        filt = db.query(SQLAFilter).filter(SQLAFilter.id == match.filter_id).first()
        result.append(match.to_pydantic(paper=paper, filt=filt))
    result.sort(key=lambda item: item.created_at, reverse=True)
    return result


def start_daily_search(
    db: Session,
    *,
    run_date: date | None = None,
) -> SQLAJob:
    requested_date = run_date or DEFAULT_DAILY_SEARCH_DATE
    if not requested_date:
        raise ValidationFailed("No daily search dates are configured")
    if not enabled_source_types(db):
        raise ValidationFailed("No data sources are enabled")

    now = datetime.now(timezone.utc)
    run = SQLASearchRun(
        id=str(uuid.uuid4()),
        status="queued",
        run_date=requested_date,
        created_at=now,
    )
    db.add(run)
    job_record = create_job(
        db,
        kind="daily_search",
        subject_type="search_run",
        subject_id=run.id,
        status="queued",
    )

    def on_failure(sess: Session, error: str) -> None:
        run.status = "failed"
        run.error = f"Could not enqueue daily search: {error}"
        run.completed_at = datetime.now(timezone.utc)
        set_job_status(job_record, status="failed", error=run.error)

    persist_then_enqueue(
        db,
        job=job_record,
        entities=(run,),
        enqueue=lambda: enqueue_for_job(
            job_record, run_daily_search, run.id, job_record.id
        ),
        on_failure=on_failure,
        log_context=f"daily search run={run.id}",
    )
    return job_record


def start_daily_summary(db: Session, search_run_id: str) -> SQLAJob:
    run = get_search_run(db, search_run_id)

    search_job = latest_job_for_subject(
        db,
        subject_type="search_run",
        subject_id=run.id,
        kind="daily_search",
    )
    if not search_job or search_job.status != "completed":
        raise ValidationFailed("Daily search must complete before starting summary")

    existing_summary = latest_job_for_subject(
        db,
        subject_type="search_run",
        subject_id=run.id,
        kind="daily_search_summary",
    )
    if existing_summary and existing_summary.status in ACTIVE_SUMMARY_JOB_STATUSES:
        raise Conflict("A summary job is already in progress for this search run")

    summary_job = create_job(
        db,
        kind="daily_search_summary",
        subject_type="search_run",
        subject_id=run.id,
        status="queued",
    )

    def on_failure(sess: Session, error: str) -> None:
        set_job_status(
            summary_job,
            status="failed",
            error=f"Could not enqueue summary: {error}",
        )

    commit_entities(db, summary_job)
    enqueue_job(
        db,
        job=summary_job,
        enqueue=lambda: enqueue_for_job(
            summary_job, summarize_daily_search, run.id, summary_job.id
        ),
        on_failure=on_failure,
        log_context=f"daily search summary run={run.id}",
    )
    return summary_job


def resolve_daily_search_job(
    db: Session, search_run_id: str, job_id: str | None
) -> SQLAJob:
    if job_id:
        job = db.query(SQLAJob).filter(SQLAJob.id == job_id).first()
        if job:
            return job
    return get_or_create_job_for_subject(
        db,
        kind="daily_search",
        subject_type="search_run",
        subject_id=search_run_id,
    )


def resolve_summary_job(db: Session, search_run_id: str, job_id: str | None) -> SQLAJob:
    if job_id:
        job = db.query(SQLAJob).filter(SQLAJob.id == job_id).first()
        if job:
            return job
    return get_or_create_job_for_subject(
        db,
        kind="daily_search_summary",
        subject_type="search_run",
        subject_id=search_run_id,
    )


def mark_running(db: Session, run: SQLASearchRun, job: SQLAJob) -> None:
    run.status = "running"
    run.started_at = datetime.now(timezone.utc)
    set_job_status(job, status="running")
    db.commit()


def set_pair_progress(
    db: Session, job: SQLAJob, *, total: int, current: int = 0
) -> None:
    from app.services.jobs import job_progress

    job.progress = job_progress(current=current, total=max(total, 1))
    db.commit()


def update_candidate_counts(
    db: Session, run: SQLASearchRun, *, candidate_count: int, candidate_counts: dict
) -> None:
    run.candidate_count = candidate_count
    run.candidate_counts = candidate_counts
    db.commit()


def set_match_count(db: Session, run: SQLASearchRun, match_count: int) -> None:
    run.match_count = match_count
    db.commit()


def commit_progress(db: Session) -> None:
    db.commit()


def complete_daily_search_job(db: Session, job: SQLAJob) -> None:
    set_job_status(job, status="completed")
    db.commit()


def fail_run(db: Session, run: SQLASearchRun, job: SQLAJob, error: str) -> None:
    run.status = "failed"
    run.error = error
    run.completed_at = datetime.now(timezone.utc)
    set_job_status(job, status="failed", error=error)
    db.commit()


def set_summary_status(
    db: Session,
    run: SQLASearchRun,
    job: SQLAJob,
    *,
    status: str,
    error: str | None = None,
) -> None:
    run.status = status
    if error is not None:
        run.error = error
    set_job_status(job, status=status, error=error)
    db.commit()


def complete_summary(
    db: Session, run: SQLASearchRun, job: SQLAJob, *, summary: str, citations: list
) -> None:
    run.summary = summary
    run.summary_citations = citations
    run.completed_at = datetime.now(timezone.utc)
    set_summary_status(db, run, job, status="completed")


def match_payloads_for_run(db: Session, search_run_id: str):
    import json

    from paper_search_core.schemas.daily_search import PaperMatchPayload

    rows = (
        db.query(SQLAPaperMatch, SQLAPaper, SQLAFilter)
        .join(SQLAPaper, SQLAPaperMatch.paper_id == SQLAPaper.id)
        .join(SQLAFilter, SQLAPaperMatch.filter_id == SQLAFilter.id)
        .filter(SQLAPaperMatch.search_run_id == search_run_id)
        .order_by(SQLAPaperMatch.created_at.asc(), SQLAPaperMatch.id.asc())
        .all()
    )
    return [
        PaperMatchPayload(
            match_id=match.id,
            paper=paper.to_search_payload(),
            filter_name=filter.name,
            result=(
                match.result
                if isinstance(match.result, str)
                else json.dumps(match.result)
                if match.result
                else ""
            ),
        )
        for match, paper, filter in rows
    ]
