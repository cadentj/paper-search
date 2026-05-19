from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.jobs.queues import enqueue_for_job
from app.models.document import SQLADocument
from app.models.job import SQLAJob
from app.services.errors import NotFound
from app.services.job_enqueue import persist_then_enqueue
from app.services.jobs import create_job, job_progress, latest_job_for_subject, set_job_status


def get_document(db: Session, document_id: str) -> SQLADocument:
    document = db.query(SQLADocument).filter(SQLADocument.id == document_id).first()
    if not document:
        raise NotFound("Document not found")
    return document


def document_payload(db: Session, document: SQLADocument):
    job = latest_job_for_subject(
        db,
        subject_type="document",
        subject_id=document.id,
        kind="document_processing",
    )
    return document.to_pydantic(job_id=job.id if job else None)


def start_document_processing(
    db: Session,
    *,
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

    def on_failure(sess: Session, error: str) -> None:
        document.status = "failed"
        document.error = f"Could not enqueue document processing: {error}"
        document.updated_at = datetime.now(timezone.utc)
        set_job_status(job_record, status="failed", error=document.error)

    def _enqueue_document_processing() -> None:
        from app.jobs.documents import process_document

        enqueue_for_job(job_record, process_document, document.id, job_record.id)

    persist_then_enqueue(
        db,
        job=job_record,
        entities=(document,),
        enqueue=_enqueue_document_processing,
        on_failure=on_failure,
        log_context=f"document={document.id}",
    )
    return document, job_record.id


def mark_document_processing(db: Session, document: SQLADocument, job: SQLAJob) -> None:
    document.status = "processing"
    document.updated_at = datetime.now(timezone.utc)
    set_job_status(job, status="running")
    db.commit()


def complete_document_needs_ocr(db: Session, document: SQLADocument, job: SQLAJob, error: str) -> None:
    document.status = "needs_ocr"
    document.error = error
    set_job_status(job, status="completed")
    db.commit()


def commit_document_progress(db: Session) -> None:
    db.commit()


def complete_document(db: Session, document: SQLADocument, job: SQLAJob, *, summary: str) -> None:
    document.summary = summary
    document.status = "ready"
    document.error = None
    document.updated_at = datetime.now(timezone.utc)
    set_job_status(job, status="completed")
    db.commit()


def fail_document(db: Session, document: SQLADocument | None, job: SQLAJob | None, error: str) -> None:
    now = datetime.now(timezone.utc)
    if document:
        document.status = "failed"
        document.error = error
        document.updated_at = now
    if job:
        set_job_status(job, status="failed", error=error)
    db.commit()
