import uuid
from datetime import datetime, timezone
from pathlib import Path

import pymupdf
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import BACKEND_DIR, settings
from app.db.session import get_db
from app.jobs.documents import process_document
from app.jobs.queue import get_queue
from app.models.document import Document
from app.schemas.documents import DocumentResponse, DocumentUploadResponse
from app.services.jobs import build_progress, create_job, latest_job_for_subject

router = APIRouter(prefix="/documents", tags=["documents"])


def _documents_dir() -> Path:
    path = Path(settings.DOCUMENT_STORAGE_DIR)
    if not path.is_absolute():
        path = BACKEND_DIR / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def _validate_pdf(content: bytes) -> int:
    if len(content) > settings.DOCUMENT_MAX_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"PDF must be {settings.DOCUMENT_MAX_SIZE_BYTES} bytes or smaller",
        )
    try:
        with pymupdf.open(stream=content, filetype="pdf") as pdf:
            page_count = len(pdf)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Could not read PDF") from exc
    if page_count > settings.DOCUMENT_MAX_PAGES:
        raise HTTPException(
            status_code=400,
            detail=f"PDF must be {settings.DOCUMENT_MAX_PAGES} pages or fewer",
        )
    return page_count


@router.post("", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if file.content_type not in {"application/pdf", "application/x-pdf"}:
        raise HTTPException(status_code=400, detail="Only PDF uploads are supported")

    content = await file.read()
    page_count = _validate_pdf(content)
    document_id = str(uuid.uuid4())
    storage_path = _documents_dir() / f"{document_id}.pdf"
    storage_path.write_bytes(content)

    now = datetime.now(timezone.utc)
    document = Document(
        id=document_id,
        original_filename=file.filename or "document.pdf",
        content_type=file.content_type or "application/pdf",
        size_bytes=len(content),
        page_count=page_count,
        storage_path=str(storage_path),
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
        progress=build_progress(
            stage="queued",
            current=0,
            total=2,
            message="Queued document processing",
        ),
    )
    db.commit()
    db.refresh(document)
    db.refresh(job_record)

    try:
        job = get_queue().enqueue(process_document, document.id, job_record.id)
        job_record.queue_job_id = getattr(job, "id", None)
        db.commit()
    except Exception as exc:
        document.status = "failed"
        document.error = f"Could not enqueue document processing: {exc}"
        document.updated_at = datetime.now(timezone.utc)
        job_record.status = "failed"
        job_record.error = document.error
        job_record.completed_at = document.updated_at
        job_record.progress = build_progress(
            stage="failed",
            current=0,
            total=2,
            message="Could not enqueue document processing. Is Redis running?",
            log=(job_record.progress or {}).get("log", []),
        )
        db.commit()
        raise HTTPException(status_code=503, detail=document.error) from exc

    payload = DocumentResponse.model_validate(document).model_dump()
    return DocumentUploadResponse(**payload, job_id=job_record.id)


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(document_id: str, db: Session = Depends(get_db)):
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return _document_payload(document, db)


def _document_payload(document: Document, db: Session) -> dict:
    payload = DocumentResponse.model_validate(document).model_dump()
    job = latest_job_for_subject(
        db,
        subject_type="document",
        subject_id=document.id,
        kind="document_processing",
    )
    payload["job_id"] = job.id if job else None
    return payload
