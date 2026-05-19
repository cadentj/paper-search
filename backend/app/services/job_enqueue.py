from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.job import SQLAJob
from app.services.jobs import set_job_status

logger = logging.getLogger(__name__)


def commit_entities(db: Session, *entities) -> None:
    db.commit()
    for entity in entities:
        if entity is not None:
            db.refresh(entity)


def enqueue_job(
    db: Session,
    *,
    job: SQLAJob,
    enqueue: Callable[[], object],
    on_failure: Callable[[Session, str], None] | None = None,
    store_queue_job_id: bool = True,
    log_context: str = "",
) -> None:
    try:
        rq_job = enqueue()
        if store_queue_job_id:
            job.queue_job_id = getattr(rq_job, "id", None)
        db.commit()
        if log_context:
            logger.info(
                "%s enqueued job=%s queue=%s", log_context, job.id, job.queue_job_id
            )
    except Exception as exc:
        error = str(exc)
        if on_failure:
            on_failure(db, error)
        else:
            set_job_status(job, status="failed", error=error)
        db.commit()
        raise ConnectionError(error) from exc


def persist_then_enqueue(
    db: Session,
    *,
    job: SQLAJob,
    enqueue: Callable[[], object],
    on_failure: Callable[[Session, str], None],
    entities: tuple = (),
    store_queue_job_id: bool = True,
    log_context: str = "",
) -> None:
    commit_entities(db, job, *entities)
    enqueue_job(
        db,
        job=job,
        enqueue=enqueue,
        on_failure=on_failure,
        store_queue_job_id=store_queue_job_id,
        log_context=log_context,
    )


def mark_job_failed(db: Session, job: SQLAJob, error: str) -> None:
    set_job_status(job, status="failed", error=error)
