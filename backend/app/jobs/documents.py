"""Document processing worker jobs."""

from datetime import datetime, timezone
from pathlib import Path

import pymupdf

from app.core.config import settings
from app.db.session import database
from app.llm.client import call_llm
from app.llm.config import SUMMARY_PROFILE
from app.llm.prompts import DOCUMENT_SUMMARY_SYSTEM_PROMPT, DOCUMENT_SUMMARY_USER_PROMPT
from app.llm.schemas import DocumentSummaryResponse
from app.models.document import Document
from app.models.job import Job
from app.services import documents as documents_service


def _now():
    return datetime.now(timezone.utc)


def _extract_text(path: Path) -> str:
    chunks: list[str] = []
    with pymupdf.open(path) as pdf:
        for page in pdf:
            chunks.append(page.get_text(sort=True))
    return "\n\n".join(chunk.strip() for chunk in chunks if chunk.strip()).strip()


def process_document(document_id: str, job_id: str) -> None:
    with database.session() as db:
        try:
            document = db.query(Document).filter(Document.id == document_id).first()
            job = db.query(Job).filter(Job.id == job_id).first()
            if not document or not job:
                return

            documents_service.mark_document_processing(db, document, job)

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
                documents_service.complete_document_needs_ocr(
                    db, document, job, "No usable embedded PDF text found."
                )
                return

            documents_service.commit_document_progress(db)

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
            documents_service.complete_document(db, document, job, summary=summary)
        except Exception as exc:
            db.rollback()
            document = db.query(Document).filter(Document.id == document_id).first()
            job = db.query(Job).filter(Job.id == job_id).first()
            documents_service.fail_document(db, document, job, str(exc))
            raise
