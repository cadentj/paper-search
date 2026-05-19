import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.jobs.queues import queue_for_kind
from app.models.job import SQLAJob


def job_progress(
    *, current: int | None = None, total: int | None = None, **extra
) -> dict:
    payload: dict = {}
    if total is not None:
        payload["total"] = max(total, 1)
    if current is not None:
        payload["current"] = current
    payload.update(extra)
    return payload


def set_job_status(
    job: SQLAJob,
    *,
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


def create_job(
    db: Session,
    *,
    kind: str,
    subject_type: str | None = None,
    subject_id: str | None = None,
    status: str = "queued",
    queue_name: str | None = None,
    progress: dict | None = None,
) -> SQLAJob:
    now = datetime.now(timezone.utc)
    job = SQLAJob(
        id=str(uuid.uuid4()),
        kind=kind,
        status=status,
        subject_type=subject_type,
        subject_id=subject_id,
        queue_name=queue_name if queue_name is not None else queue_for_kind(kind),
        progress=progress or {},
        created_at=now,
    )
    db.add(job)
    return job


def latest_job_for_subject(
    db: Session,
    *,
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


def get_or_create_job_for_subject(
    db: Session,
    *,
    kind: str,
    subject_type: str,
    subject_id: str,
) -> SQLAJob:
    job = latest_job_for_subject(
        db,
        subject_type=subject_type,
        subject_id=subject_id,
        kind=kind,
    )
    if job:
        return job
    return create_job(
        db,
        kind=kind,
        subject_type=subject_type,
        subject_id=subject_id,
    )
