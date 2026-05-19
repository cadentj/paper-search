"""Document processing worker jobs."""

from datetime import datetime, timezone
from pathlib import Path

import pymupdf

from app.core.config import settings
from app.db.session import SessionLocal
from app.llm.client import call_llm
from app.llm.config import SUMMARY_PROFILE
from app.llm.prompts import DOCUMENT_SUMMARY_SYSTEM_PROMPT, DOCUMENT_SUMMARY_USER_PROMPT
from app.llm.schemas import DocumentSummaryResponse
from app.models.document import Document
from app.models.job import Job
from app.services.jobs import set_job_status


def _now():
    return datetime.now(timezone.utc)


def _extract_text(path: Path) -> str:
    chunks: list[str] = []
    with pymupdf.open(path) as pdf:
        for page in pdf:
            chunks.append(page.get_text(sort=True))
    return "\n\n".join(chunk.strip() for chunk in chunks if chunk.strip()).strip()


def process_document(document_id: str, job_id: str) -> None:
    db = SessionLocal()
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        job = db.query(Job).filter(Job.id == job_id).first()
        if not document or not job:
            return

        document.status = "processing"
        document.updated_at = _now()
        set_job_status(job, status="running")
        db.commit()

        pdf_path = Path(document.storage_path)
        text = _extract_text(pdf_path)
        text_path = pdf_path.with_suffix(".txt")
        text_path.write_text(text, encoding="utf-8")

        document = db.query(Document).filter(Document.id == document_id).first()
        job = db.query(Job).filter(Job.id == job_id).first()
        if not document or not job:
            return
        document.extracted_text_path = str(text_path)
        document.updated_at = _now()

        if len(text) < settings.DOCUMENT_MIN_TEXT_CHARS:
            document.status = "needs_ocr"
            document.error = "No usable embedded PDF text found."
            set_job_status(job, status="completed")
            db.commit()
            return

        db.commit()

        summary_input = text[: settings.DOCUMENT_SUMMARY_MAX_CHARS]
        result = call_llm(
            DOCUMENT_SUMMARY_SYSTEM_PROMPT,
            DOCUMENT_SUMMARY_USER_PROMPT.format(
                filename=document.original_filename,
                document_text=summary_input,
            ),
            response_model=DocumentSummaryResponse,
            profile=SUMMARY_PROFILE,
        )
        summary = result["content"].get("summary", "").strip()
        if not summary:
            raise RuntimeError("Document summary was empty")

        document = db.query(Document).filter(Document.id == document_id).first()
        job = db.query(Job).filter(Job.id == job_id).first()
        if not document or not job:
            return
        document.summary = summary
        document.status = "ready"
        document.error = None
        document.updated_at = _now()
        set_job_status(job, status="completed")
        db.commit()
    except Exception as exc:
        db.rollback()
        document = db.query(Document).filter(Document.id == document_id).first()
        job = db.query(Job).filter(Job.id == job_id).first()
        now = _now()
        if document:
            document.status = "failed"
            document.error = str(exc)
            document.updated_at = now
        if job:
            set_job_status(job, status="failed", error=str(exc))
        db.commit()
        raise
    finally:
        db.close()
