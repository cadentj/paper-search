"""Scholar profile import worker job."""

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from app.db.session import database
from app.models.filter import SQLAFilter
from app.models.job import SQLAJob
from app.models.research_profile_import import SQLAResearchProfileImport
from app.services.jobs import set_job_status
from app.services.semantic_scholar import get_author_papers, build_publications_text
from app.llm.client import async_call_llm
from app.llm.config import FILTER_GENERATION_PROFILE
from app.llm.prompts import SCHOLAR_PROFILE_SYSTEM_PROMPT, SCHOLAR_PROFILE_USER_PROMPT
from app.llm.schemas import OnboardingFiltersResponse

logger = logging.getLogger(__name__)


def run_scholar_import(import_id: str, job_id: str) -> None:
    with database.session() as db:
        try:
            job = db.query(SQLAJob).filter(SQLAJob.id == job_id).first()
            if not job:
                return
            set_job_status(job, status="running")

            profile_import = (
                db.query(SQLAResearchProfileImport)
                .filter(SQLAResearchProfileImport.id == import_id)
                .first()
            )
            if not profile_import:
                set_job_status(job, status="failed", error="Import not found")
                db.commit()
                return

            profile_import.status = "running"
            db.commit()

            author_id = profile_import.external_author_id
            if not author_id:
                profile_import.status = "failed"
                profile_import.error = "No author ID"
                set_job_status(job, status="failed", error="No author ID")
                db.commit()
                return

            papers = get_author_papers(author_id)
            profile_import.publications = [
                {
                    "title": p.get("title"),
                    "year": p.get("year"),
                    "abstract": (p.get("abstract") or "")[:300],
                }
                for p in papers
            ]
            db.commit()

            if not papers:
                profile_import.status = "completed"
                set_job_status(job, status="completed")
                db.commit()
                return

            publications_text = build_publications_text(papers)
            fields = set()
            for p in papers:
                for f in p.get("fieldsOfStudy") or []:
                    fields.add(f)

            user_prompt = SCHOLAR_PROFILE_USER_PROMPT.format(
                author_name=profile_import.display_name or "Unknown",
                fields_of_study=", ".join(sorted(fields))
                if fields
                else "Not specified",
                publications_text=publications_text,
            )

            result = asyncio.run(
                async_call_llm(
                    system_prompt=SCHOLAR_PROFILE_SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    response_model=OnboardingFiltersResponse,
                    profile=FILTER_GENERATION_PROFILE,
                )
            )

            proposed = result["content"].get("proposedFilters", [])
            now = datetime.now(timezone.utc)

            for raw in proposed[:10]:
                filter = SQLAFilter(
                    id=str(uuid.uuid4()),
                    name=raw.get("name", "Unnamed Filter"),
                    definition={
                        "name": raw.get("name", "Unnamed Filter"),
                        "description": raw.get("description", ""),
                        "mode": raw.get("mode", "topic"),
                    },
                    status="draft",
                    source="scholar",
                    created_at=now,
                    updated_at=now,
                )
                db.add(filter)

            profile_import.status = "completed"
            set_job_status(job, status="completed")
            db.commit()

        except Exception as e:
            db.rollback()
            profile_import = (
                db.query(SQLAResearchProfileImport)
                .filter(SQLAResearchProfileImport.id == import_id)
                .first()
            )
            if profile_import:
                profile_import.status = "failed"
                profile_import.error = str(e)
            job = db.query(SQLAJob).filter(SQLAJob.id == job_id).first()
            if job:
                set_job_status(job, status="failed", error=str(e))
            db.commit()
            logger.exception("scholar_import import=%s failed", import_id)
