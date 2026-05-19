import logging
import uuid
from datetime import datetime, timezone

from redis import Redis
from rq import Queue
from sqlalchemy.orm import Session

from app.config import settings
from app.jobs.queues import queue_for_kind
from app.models.document import SQLADocument
from app.models.idea_map import SQLAIdeaMap
from app.models.job import Job, SQLAJob
from app.models.onboarding_extraction import SQLAOnboardingExtraction
from app.models.research_profile_import import SQLAResearchProfileImport
from app.models.search_run import SQLASearchRun

logger = logging.getLogger(__name__)

DONE_STATUSES = frozenset({"completed", "failed", "skipped"})
ACTIVE_JOB_STATUSES = frozenset({"queued", "running"})
SUMMARY_JOB_MAX_SECONDS = 600

STALE_JOB_MAX_SECONDS_BY_KIND: dict[str, int] = {
    "daily_search_summary": SUMMARY_JOB_MAX_SECONDS,
}

_SUBJECT_MODELS_BY_KIND = {
    "document_processing": SQLADocument,
    "idea_map": SQLAIdeaMap,
    "daily_search": SQLASearchRun,
    "daily_search_summary": SQLASearchRun,
    "onboarding_extraction": SQLAOnboardingExtraction,
    "scholar_import": SQLAResearchProfileImport,
}


def get_job(db: Session, job_id: str) -> SQLAJob | None:
    return db.query(SQLAJob).filter(SQLAJob.id == job_id).first()


def get_job_of_kind(db: Session, job_id: str, kind: str) -> SQLAJob | None:
    job = get_job(db, job_id)
    if not job or job.kind != kind:
        return None
    return job


def is_done(job: SQLAJob) -> bool:
    return job.status in DONE_STATUSES


def with_progress(job: SQLAJob, **fields) -> Job:
    response = job.to_pydantic()
    progress = dict(response.progress or {})
    progress.update(fields)
    response.progress = progress
    return response


def job_progress(current: int | None = None, total: int | None = None, **extra) -> dict:
    payload: dict = {}
    if total is not None:
        payload["total"] = max(total, 1)
    if current is not None:
        payload["current"] = current
    payload.update(extra)
    return payload


def set_job_status(
    job: SQLAJob,
    status: str,
    error: str | None = None,
) -> None:
    now = datetime.now(timezone.utc)
    job.status = status
    if error is not None:
        job.error = error
    if status == "running" and not job.started_at:
        job.started_at = now
    if status in {"completed", "failed", "skipped"}:
        job.completed_at = now


def commit_refresh(db: Session, *entities) -> None:
    db.commit()
    for entity in entities:
        if entity is not None:
            db.refresh(entity)


def create_job(
    db: Session,
    kind: str,
    subject_type: str | None = None,
    subject_id: str | None = None,
    status: str = "queued",
    queue_name: str | None = None,
    progress: dict | None = None,
    payload: dict | None = None,
) -> SQLAJob:
    now = datetime.now(timezone.utc)
    job = SQLAJob(
        id=str(uuid.uuid4()),
        kind=kind,
        status=status,
        subject_type=subject_type,
        subject_id=subject_id,
        queue_name=queue_name if queue_name is not None else queue_for_kind(kind),
        payload=payload or {},
        progress=progress or {},
        created_at=now,
    )
    db.add(job)
    return job


def reconcile_stale_job(db: Session, job: SQLAJob) -> bool:
    """Mark queued/running jobs failed when they exceed per-kind max age."""
    if job.status not in ACTIVE_JOB_STATUSES:
        return False

    max_age_seconds = STALE_JOB_MAX_SECONDS_BY_KIND.get(job.kind)
    if not max_age_seconds:
        return False

    now = datetime.now(timezone.utc)
    started_at = job.started_at or job.created_at
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    if (now - started_at).total_seconds() <= max_age_seconds:
        return False

    error = "Job timed out"
    set_job_status(job, status="failed", error=error)
    run: SQLASearchRun | None = None
    if job.kind == "daily_search_summary" and job.subject_id:
        run = db.get(SQLASearchRun, job.subject_id)
        if run and run.status == "running":
            run.status = "failed"
            run.error = error
            run.completed_at = now
    commit_refresh(db, job, run)
    return True


def latest_job_for_subject(
    db: Session,
    subject_type: str,
    subject_id: str,
    kind: str | None = None,
) -> SQLAJob | None:
    query = db.query(SQLAJob).filter(
        SQLAJob.subject_type == subject_type,
        SQLAJob.subject_id == subject_id,
    )
    if kind:
        query = query.filter(SQLAJob.kind == kind)
    return query.order_by(SQLAJob.created_at.desc()).first()


def _sync_subject_failure(db: Session, job: SQLAJob, error: str) -> None:
    model = _SUBJECT_MODELS_BY_KIND.get(job.kind)
    if not model or not job.subject_id:
        return
    subject = db.get(model, job.subject_id)
    if not subject:
        return
    subject.status = "failed"
    if hasattr(subject, "error"):
        subject.error = error
    now = datetime.now(timezone.utc)
    if hasattr(subject, "updated_at"):
        subject.updated_at = now
    if hasattr(subject, "completed_at"):
        subject.completed_at = now


def _dispatcher_run_job():
    from app.jobs.dispatcher import run_job

    return run_job


def enqueue(
    db: Session,
    job: SQLAJob,
    *,
    log_context: str = "",
    job_timeout: int | None = None,
) -> None:
    try:
        db.commit()
        run_job = _dispatcher_run_job()
        queue = Queue(job.queue_name, connection=Redis.from_url(settings.REDIS_URL))
        enqueue_kwargs: dict = {}
        if job_timeout is not None:
            enqueue_kwargs["job_timeout"] = job_timeout
        queue.enqueue(run_job, job.id, **enqueue_kwargs)
        if log_context:
            logger.info(
                "%s enqueued job=%s queue=%s",
                log_context,
                job.id,
                job.queue_name,
            )
    except Exception as exc:
        error = str(exc)
        db.rollback()
        set_job_status(job, status="failed", error=error)
        _sync_subject_failure(db, job, error)
        db.commit()
        raise ConnectionError(error) from exc
