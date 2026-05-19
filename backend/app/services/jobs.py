import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.job import Job


def job_progress(*, current: int | None = None, total: int | None = None, **extra) -> dict:
    payload: dict = {}
    if total is not None:
        payload["total"] = max(total, 1)
    if current is not None:
        payload["current"] = current
    payload.update(extra)
    return payload


def set_job_status(
    job: Job,
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
    queue_name: str | None = "default",
    progress: dict | None = None,
) -> Job:
    now = datetime.now(timezone.utc)
    job = Job(
        id=str(uuid.uuid4()),
        kind=kind,
        status=status,
        subject_type=subject_type,
        subject_id=subject_id,
        queue_name=queue_name,
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
) -> Job | None:
    query = db.query(Job).filter(
        Job.subject_type == subject_type,
        Job.subject_id == subject_id,
    )
    if kind:
        query = query.filter(Job.kind == kind)
    return query.order_by(Job.created_at.desc()).first()


def get_or_create_job_for_subject(
    db: Session,
    *,
    kind: str,
    subject_type: str,
    subject_id: str,
) -> Job:
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
