from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.document import SQLADocument
from app.models.job import Job, SQLAJob
from app.services.jobs import (
    commit_refresh,
    create_job,
    enqueue,
    job_progress,
    latest_job_for_subject,
    set_job_status,
    with_progress,
)


def get_document(db: Session, document_id: str) -> SQLADocument | None:
    return db.query(SQLADocument).filter(SQLADocument.id == document_id).first()


def get_document_for_job(db: Session, job: SQLAJob) -> SQLADocument | None:
    if not job.subject_id:
        return None
    return db.query(SQLADocument).filter(SQLADocument.id == job.subject_id).first()


def serialize_document_job(job: SQLAJob, document: SQLADocument) -> Job:
    if document.status in {"ready", "needs_ocr", "failed"}:
        current, total = 2, 2
    elif document.status == "processing":
        current, total = 1, 2
    else:
        current, total = 0, 2
    return with_progress(job, current=current, total=total)


def get_document_payload(db: Session, document: SQLADocument):
    job = latest_job_for_subject(
        db,
        subject_type="document",
        subject_id=document.id,
        kind="document_processing",
    )
    return document.to_pydantic(job_id=job.id if job else None)


def start_document_processing(
    db: Session,
    document_id: str,
    original_filename: str,
    content_type: str,
    size_bytes: int,
    page_count: int,
    storage_path: str,
) -> tuple[SQLADocument, str]:
    now = datetime.now(timezone.utc)
    document = SQLADocument(
        id=document_id,
        original_filename=original_filename,
        content_type=content_type,
        size_bytes=size_bytes,
        page_count=page_count,
        storage_path=storage_path,
        status="queued",
        created_at=now,
        updated_at=now,
    )
    db.add(document)
    job_record = create_job(
        db,
        kind="document_processing",
        subject_type="document",
        subject_id=document.id,
        status="queued",
        progress=job_progress(total=2),
    )
    commit_refresh(db, document, job_record)
    enqueue(db, job_record, log_context=f"document={document.id}")
    return document, job_record.id


def mark_document_processing(db: Session, document: SQLADocument, job: SQLAJob) -> None:
    document.status = "processing"
    document.updated_at = datetime.now(timezone.utc)
    set_job_status(job, status="running")
    db.commit()


def complete_document_needs_ocr(
    db: Session, document: SQLADocument, job: SQLAJob, error: str
) -> None:
    document.status = "needs_ocr"
    document.error = error
    set_job_status(job, status="completed")
    db.commit()


def commit_document_progress(db: Session) -> None:
    db.commit()


def complete_document(
    db: Session, document: SQLADocument, job: SQLAJob, summary: str
) -> None:
    document.summary = summary
    document.status = "ready"
    document.error = None
    document.updated_at = datetime.now(timezone.utc)
    set_job_status(job, status="completed")
    db.commit()


def fail_document(
    db: Session, document: SQLADocument | None, job: SQLAJob | None, error: str
) -> None:
    now = datetime.now(timezone.utc)
    if document:
        document.status = "failed"
        document.error = error
        document.updated_at = now
    if job:
        set_job_status(job, status="failed", error=error)
    db.commit()
