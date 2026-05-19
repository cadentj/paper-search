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


def fail_enqueue(db: Session, job: SQLAJob, error: str) -> None:
    now = datetime.now(timezone.utc)
    set_job_status(job, status="failed", error=error)

    if job.kind == "document_processing" and job.subject_id:
        document = db.get(SQLADocument, job.subject_id)
        if document:
            document.status = "failed"
            document.error = f"Could not enqueue document processing: {error}"
            document.updated_at = now
    elif job.kind == "idea_map" and job.subject_id:
        idea_map = db.get(SQLAIdeaMap, job.subject_id)
        if idea_map:
            idea_map.status = "failed"
            idea_map.error = f"Could not enqueue idea map generation: {error}"
            idea_map.updated_at = now
    elif job.kind == "daily_search" and job.subject_id:
        run = db.get(SQLASearchRun, job.subject_id)
        if run:
            run.status = "failed"
            run.error = f"Could not enqueue daily search: {error}"
            run.completed_at = now
    elif job.kind == "onboarding_extraction" and job.subject_id:
        extraction = db.get(SQLAOnboardingExtraction, job.subject_id)
        if extraction:
            extraction.status = "failed"
            extraction.error = f"Could not enqueue onboarding extraction: {error}"
            extraction.updated_at = now
    elif job.kind == "scholar_import" and job.subject_id:
        profile_import = db.get(SQLAResearchProfileImport, job.subject_id)
        if profile_import:
            profile_import.status = "failed"
            profile_import.error = error
    elif job.kind == "onboarding_generation":
        job.error = f"Could not enqueue onboarding generation: {error}"
    elif job.kind == "daily_search_summary":
        job.error = f"Could not enqueue summary: {error}"


def enqueue(db: Session, job: SQLAJob, *, log_context: str = "") -> None:
    from app.jobs.dispatcher import run_job

    db.commit()
    try:
        queue = Queue(job.queue_name, connection=Redis.from_url(settings.REDIS_URL))
        queue.enqueue(run_job, job.id)
        if log_context:
            logger.info(
                "%s enqueued job=%s queue=%s",
                log_context,
                job.id,
                job.queue_name,
            )
    except Exception as exc:
        error = str(exc)
        fail_enqueue(db, job, error)
        db.commit()
        raise ConnectionError(error) from exc
