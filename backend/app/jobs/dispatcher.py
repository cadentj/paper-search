"""Central RQ entrypoint: load job by id and dispatch to kind handler."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.jobs import (
    daily_search,
    daily_search_summary,
    feedback_reflection,
    idea_map,
    onboarding,
    scholar_import,
)
from app.models.job import SQLAJob
from app.services.jobs import set_job_status

Handler = Callable[[Session, SQLAJob], None]

HANDLERS: dict[str, Handler] = {
    "idea_map": idea_map.run,
    "daily_search": daily_search.run,
    "daily_search_summary": daily_search_summary.run,
    "feedback_reflection": feedback_reflection.run,
    "onboarding_generation": onboarding.run_generation,
    "onboarding_extraction": onboarding.run_extraction,
    "scholar_import": scholar_import.run,
}


def run_job(job_id: str) -> None:
    from app.db.session import database

    with database.session() as db:
        job = db.get(SQLAJob, job_id)
        if not job:
            return
        handler = HANDLERS.get(job.kind)
        if not handler:
            set_job_status(job, status="failed", error=f"Unknown job kind: {job.kind}")
            db.commit()
            return
        handler(db, job)
