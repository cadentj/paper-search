"""Paper notes filter generation worker job."""

import logging
import uuid
from datetime import datetime, timezone

from app.db.session import database
from app.models.filter import SQLAFilter
from app.models.job import SQLAJob
from app.models.paper import SQLAPaper
from app.models.paper_note import SQLAPaperNote
from app.services.jobs import set_job_status
from app.llm.client import call_llm
from app.llm.config import FILTER_GENERATION_PROFILE
from app.llm.prompts import PAPER_NOTES_SYSTEM_PROMPT, PAPER_NOTES_USER_PROMPT
from app.llm.schemas import PaperNotesFilterGenResponse

logger = logging.getLogger(__name__)


def generate_filters_from_notes(note_id: str, job_id: str) -> None:
    with database.session() as db:
        try:
            job = db.query(SQLAJob).filter(SQLAJob.id == job_id).first()
            if not job:
                return
            set_job_status(job, status="running")
            db.commit()

            note = db.query(SQLAPaperNote).filter(SQLAPaperNote.id == note_id).first()
            if not note:
                set_job_status(job, status="failed", error="Note not found")
                db.commit()
                return

            paper = db.query(SQLAPaper).filter(SQLAPaper.id == note.paper_id).first()
            if not paper:
                set_job_status(job, status="failed", error="Paper not found")
                db.commit()
                return

            user_prompt = PAPER_NOTES_USER_PROMPT.format(
                paper_title=paper.title or "Unknown",
                paper_authors=", ".join(paper.authors) if paper.authors else "Unknown",
                paper_abstract=paper.abstract or "(no abstract)",
                notes_text=note.text,
            )

            result = call_llm(
                system_prompt=PAPER_NOTES_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                response_model=PaperNotesFilterGenResponse,
                profile=FILTER_GENERATION_PROFILE,
            )

            proposed = result["content"].get("proposedFilters", [])
            now = datetime.now(timezone.utc)

            for raw in proposed[:5]:
                filt = SQLAFilter(
                    id=str(uuid.uuid4()),
                    name=raw.get("name", "Unnamed Filter"),
                    definition={
                        "name": raw.get("name", "Unnamed Filter"),
                        "description": raw.get("description", ""),
                        "mode": raw.get("mode", "topic"),
                    },
                    status="draft",
                    source="paper_notes",
                    created_at=now,
                    updated_at=now,
                )
                db.add(filt)

            set_job_status(job, status="completed")
            db.commit()

        except Exception as e:
            db.rollback()
            job = db.query(SQLAJob).filter(SQLAJob.id == job_id).first()
            if job:
                set_job_status(job, status="failed", error=str(e))
                db.commit()
            logger.exception("paper_notes_filter_gen note=%s failed", note_id)
