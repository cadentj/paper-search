from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.document import SQLADocument
from app.models.idea_map import SQLAIdeaMap
from app.models.job import Job, SQLAJob
from paper_search_core.models.paper import SQLAPaper
from app.models.search_run import SQLASearchRun
from app.services import job_views

RECENT_JOBS_LIMIT = 15
ACTIVE_STATUSES = ("queued", "running")
DONE_STATUSES = tuple(job_views.DONE_STATUSES)


@dataclass(frozen=True)
class JobOverviewEntry:
    job: Job
    label: str
    detail: str | None = None
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


def list_recent_jobs(db: Session, *, limit: int = RECENT_JOBS_LIMIT) -> list[SQLAJob]:
    completed_at = func.coalesce(SQLAJob.completed_at, SQLAJob.created_at)
    return (
        db.query(SQLAJob)
        .filter(SQLAJob.status.in_(DONE_STATUSES))
        .order_by(completed_at.desc(), SQLAJob.id.desc())
        .limit(limit)
        .all()
    )


def _load_search_runs(db: Session, jobs: list[SQLAJob]) -> dict[str, SQLASearchRun]:
    run_ids = [
        job.subject_id
        for job in jobs
        if job.kind in ("daily_search", "daily_search_summary") and job.subject_id
    ]
    if not run_ids:
        return {}
    runs = db.query(SQLASearchRun).filter(SQLASearchRun.id.in_(run_ids)).all()
    return {run.id: run for run in runs}


def _load_idea_maps(db: Session, jobs: list[SQLAJob]) -> dict[str, SQLAIdeaMap]:
    idea_map_ids = [
        job.subject_id for job in jobs if job.kind == "idea_map" and job.subject_id
    ]
    if not idea_map_ids:
        return {}
    idea_maps = db.query(SQLAIdeaMap).filter(SQLAIdeaMap.id.in_(idea_map_ids)).all()
    return {item.id: item for item in idea_maps}


def _load_papers(db: Session, paper_ids: list[str]) -> dict[str, SQLAPaper]:
    if not paper_ids:
        return {}
    papers = db.query(SQLAPaper).filter(SQLAPaper.id.in_(paper_ids)).all()
    return {paper.id: paper for paper in papers}


def _load_documents(db: Session, jobs: list[SQLAJob]) -> dict[str, SQLADocument]:
    document_ids = [
        job.subject_id
        for job in jobs
        if job.kind == "document_processing" and job.subject_id
    ]
    if not document_ids:
        return {}
    documents = db.query(SQLADocument).filter(SQLADocument.id.in_(document_ids)).all()
    return {doc.id: doc for doc in documents}


def serialize_job_for_overview(db: Session, job: SQLAJob) -> Job:
    if job.kind == "daily_search":
        run = job_views.get_search_run_for_job(db, job)
        return job_views.serialize_daily_search_job(db, job, run)
    if job.kind == "idea_map":
        idea_map = job_views.get_idea_map_for_job(db, job)
        return job_views.serialize_idea_map_job(db, job, idea_map)
    if job.kind == "onboarding_generation":
        return job_views.serialize_onboarding_generation_job(db, job)
    if job.kind == "onboarding_extraction":
        extraction = job_views.get_extraction_for_job(db, job)
        return job_views.serialize_onboarding_extraction_job(db, job, extraction)
    if job.kind == "document_processing":
        document = job_views.get_document_for_job(db, job)
        return job_views.serialize_document_job(job, document)
    return job.to_pydantic()


def _hydrate_entry(
    db: Session,
    job: SQLAJob,
    *,
    search_runs: dict[str, SQLASearchRun],
    idea_maps: dict[str, SQLAIdeaMap],
    papers: dict[str, SQLAPaper],
    documents: dict[str, SQLADocument],
) -> JobOverviewEntry:
    kind = job.kind
    label = kind.replace("_", " ").title()
    detail: str | None = None
    href: str | None = None

    if kind == "daily_search":
        label = "Daily search"
        href = "/dashboard/daily/report"
        run = search_runs.get(job.subject_id or "")
        if run:
            detail = run.run_date.isoformat()
    elif kind == "daily_search_summary":
        label = "Daily report summary"
        href = "/dashboard/daily/report"
        run = search_runs.get(job.subject_id or "")
        if run:
            detail = run.run_date.isoformat()
    elif kind == "idea_map":
        label = "Idea map"
        idea_map = idea_maps.get(job.subject_id or "")
        if idea_map:
            href = f"/dashboard/papers/{idea_map.paper_id}"
            paper = papers.get(idea_map.paper_id)
            if paper:
                detail = paper.title
    elif kind == "feedback_reflection":
        label = "Processing feedback"
        href = "/dashboard/filters"
    elif kind == "onboarding_generation":
        label = "Generating filters"
        href = "/dashboard/filters"
    elif kind == "onboarding_extraction":
        label = "Extracting filters"
        href = "/dashboard/filters"
    elif kind == "document_processing":
        label = "Document processing"
        href = "/dashboard/settings"
        document = documents.get(job.subject_id or "")
        if document:
            detail = document.original_filename
    elif kind == "scholar_import":
        label = "Scholar import"
        href = "/dashboard/settings"

    try:
        serialized_job = serialize_job_for_overview(db, job)
    except Exception:
        serialized_job = job.to_pydantic()

    return JobOverviewEntry(
        job=serialized_job,
        label=label,
        detail=detail,
        href=href,
    )


def build_overview_entries(db: Session, jobs: list[SQLAJob]) -> list[JobOverviewEntry]:
    if not jobs:
        return []
    search_runs = _load_search_runs(db, jobs)
    idea_maps = _load_idea_maps(db, jobs)
    paper_ids = [item.paper_id for item in idea_maps.values()]
    papers = _load_papers(db, paper_ids)
    documents = _load_documents(db, jobs)
    return [
        _hydrate_entry(
            db,
            job,
            search_runs=search_runs,
            idea_maps=idea_maps,
            papers=papers,
            documents=documents,
        )
        for job in jobs
    ]


def jobs_overview(db: Session) -> JobsOverview:
    active_jobs = list_active_jobs(db)
    recent_jobs = list_recent_jobs(db)
    return JobsOverview(
        active=build_overview_entries(db, active_jobs),
        recent=build_overview_entries(db, recent_jobs),
    )
