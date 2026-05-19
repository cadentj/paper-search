from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.idea_map import SQLAIdeaMap
from app.models.job import Job, SQLAJob
from app.services import documents, onboarding, papers, search_runs
from app.services.jobs import DONE_STATUSES, with_progress

RECENT_JOBS_LIMIT = 15
ACTIVE_STATUSES = ("queued", "running")


@dataclass(frozen=True)
class JobOverviewEntry:
    job: Job
    href: str | None = None


@dataclass(frozen=True)
class JobsOverview:
    active: list[JobOverviewEntry]
    recent: list[JobOverviewEntry]


def list_active_jobs(db: Session) -> list[SQLAJob]:
    return (
        db.query(SQLAJob)
        .filter(SQLAJob.status.in_(ACTIVE_STATUSES))
        .order_by(SQLAJob.created_at.desc())
        .all()
    )


def list_recent_jobs(db: Session, limit: int = RECENT_JOBS_LIMIT) -> list[SQLAJob]:
    completed_at = func.coalesce(SQLAJob.completed_at, SQLAJob.created_at)
    return (
        db.query(SQLAJob)
        .filter(SQLAJob.status.in_(DONE_STATUSES))
        .order_by(completed_at.desc(), SQLAJob.id.desc())
        .limit(limit)
        .all()
    )


def _load_idea_maps(db: Session, jobs: list[SQLAJob]) -> dict[str, SQLAIdeaMap]:
    idea_map_ids = [
        job.subject_id for job in jobs if job.kind == "idea_map" and job.subject_id
    ]
    if not idea_map_ids:
        return {}
    idea_maps = db.query(SQLAIdeaMap).filter(SQLAIdeaMap.id.in_(idea_map_ids)).all()
    return {item.id: item for item in idea_maps}


def serialize_job_for_overview(db: Session, job: SQLAJob) -> Job:
    if job.kind == "daily_search":
        run = search_runs.get_search_run_for_job(db, job)
        if run:
            return search_runs.serialize_daily_search_job(db, job, run)
    elif job.kind == "idea_map":
        idea_map = papers.get_idea_map_for_job(db, job)
        if idea_map:
            return papers.serialize_idea_map_job(db, job, idea_map)
    elif job.kind == "onboarding_generation":
        count = len(onboarding.draft_filters_for_generation(db, job.id))
        return with_progress(job, current=count, total=max(count, 1))
    elif job.kind == "onboarding_extraction":
        extraction = onboarding.get_extraction_for_job(db, job)
        if extraction:
            count = len(extraction.proposed_filters or [])
            return with_progress(job, current=count, total=max(count, 1))
    elif job.kind == "document_processing":
        document = documents.get_document_for_job(db, job)
        if document:
            return documents.serialize_document_job(job, document)
    return job.to_pydantic()


def build_overview_entries(db: Session, jobs: list[SQLAJob]) -> list[JobOverviewEntry]:
    if not jobs:
        return []
    idea_maps = _load_idea_maps(db, jobs)
    entries: list[JobOverviewEntry] = []
    for job in jobs:
        href: str | None = None
        if job.kind == "idea_map" and job.subject_id:
            idea_map = idea_maps.get(job.subject_id)
            if idea_map:
                href = f"/dashboard/papers/{idea_map.paper_id}"
        entries.append(
            JobOverviewEntry(
                job=serialize_job_for_overview(db, job),
                href=href,
            )
        )
    return entries


def jobs_overview(db: Session) -> JobsOverview:
    active_jobs = list_active_jobs(db)
    recent_jobs = list_recent_jobs(db)
    return JobsOverview(
        active=build_overview_entries(db, active_jobs),
        recent=build_overview_entries(db, recent_jobs),
    )
