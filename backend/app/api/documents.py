import uuid
from pathlib import Path

import pymupdf
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.http_errors import raise_http_from_service
from app.config import BACKEND_DIR, settings
from app.db.session import get_db
from app.models.document import Document
from app.services import documents as documents_service

router = APIRouter(prefix="/documents", tags=["documents"])


class DocumentUpload(Document):
    job_id: str


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


@router.post("", response_model=DocumentUpload)
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

    try:
        document, job_id = documents_service.start_document_processing(
            db,
            document_id=document_id,
            original_filename=file.filename or "document.pdf",
            content_type=file.content_type or "application/pdf",
            size_bytes=len(content),
            page_count=page_count,
            storage_path=str(storage_path),
        )
    except Exception as exc:
        raise_http_from_service(exc)

    return DocumentUpload(
        **document.to_pydantic().model_dump(),
        job_id=job_id,
    )


@router.get("/{document_id}", response_model=Document)
def get_document(document_id: str, db: Session = Depends(get_db)):
    try:
        document = documents_service.get_document(db, document_id)
    except Exception as exc:
        raise_http_from_service(exc)
    return documents_service.document_payload(db, document)
