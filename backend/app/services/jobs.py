import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.job import Job
from app.schemas.jobs import JobProgress


def build_progress(
    *,
    stage: str,
    current: int,
    total: int,
    message: str,
    log: list[dict] | None = None,
    append_log: bool = True,
    **extra,
) -> dict:
    entries = list(log or [])
    if append_log:
        entries.append(
            {
                "at": datetime.now(timezone.utc).isoformat(),
                "stage": stage,
                "message": message,
            }
        )

    payload = {
        "stage": stage,
        "current": current,
        "total": max(total, 1),
        "message": message,
        "log": entries[-50:],
        **extra,
    }
    return JobProgress.model_validate(payload).model_dump(mode="json")


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
        progress=progress or build_progress(
            stage=status,
            current=0,
            total=1,
            message=status.title(),
        ),
        created_at=now,
        updated_at=now,
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
