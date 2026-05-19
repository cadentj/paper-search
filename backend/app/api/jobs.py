from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.document import Document
from app.models.filter import Filter
from app.models.idea_map import IdeaMap
from app.models.job import Job
from app.models.onboarding_extraction import OnboardingExtraction
from app.models.paper_match import PaperMatch
from app.models.search_run import SearchRun
from app.services import job_views
from app.services.jobs_overview import jobs_overview
from app.services.search_runs import search_run_payload, summary_payload

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobProgress(BaseModel):
    current: int = 0
    total: int = 1

    model_config = ConfigDict(extra="allow")


class JobStart(BaseModel):
    job_id: str


class DailySearchJob(BaseModel):
    job: Job
    subject: SearchRun
    items: list[PaperMatch] = Field(default_factory=list)
    next_cursor: str | None = None
    done: bool = False


class DailySearchSummaryJob(BaseModel):
    job: Job
    run: SearchRun
    summary: "DailySearchSummary | None" = None
    done: bool = False


class IdeaMapJob(BaseModel):
    job: Job
    subject: IdeaMap
    items: list[dict] = Field(default_factory=list)
    next_cursor: str | None = None
    done: bool = False


class OnboardingGenerationJob(BaseModel):
    job: Job
    subject: Job
    items: list[Filter] = Field(default_factory=list)
    next_cursor: str | None = None
    done: bool = False


class OnboardingExtractionJob(BaseModel):
    job: Job
    subject: OnboardingExtraction
    items: list[dict] = Field(default_factory=list)
    next_cursor: str | None = None
    done: bool = False


class DocumentProcessingJob(BaseModel):
    job: Job
    subject: Document
    items: list[dict] = Field(default_factory=list)
    next_cursor: str | None = None
    done: bool = False


class JobOverviewResponse(BaseModel):
    job: Job
    label: str
    detail: str | None = None
    href: str | None = None


class JobsOverviewResponse(BaseModel):
    active: list[JobOverviewResponse] = Field(default_factory=list)
    recent: list[JobOverviewResponse] = Field(default_factory=list)


@router.get("/overview", response_model=JobsOverviewResponse)
def get_jobs_overview(db: Session = Depends(get_db)):
    overview = jobs_overview(db)
    return JobsOverviewResponse(
        active=[
            JobOverviewResponse(
                job=entry.job,
                label=entry.label,
                detail=entry.detail,
                href=entry.href,
            )
            for entry in overview.active
        ],
        recent=[
            JobOverviewResponse(
                job=entry.job,
                label=entry.label,
                detail=entry.detail,
                href=entry.href,
            )
            for entry in overview.recent
        ],
    )


@router.get("/{job_id}", response_model=Job)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = job_views.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_pydantic()


@router.get("/daily-search/{job_id}", response_model=DailySearchJob)
def get_daily_search_job(
    job_id: str,
    cursor: str | None = None,
    db: Session = Depends(get_db),
):
    job = job_views.get_job_of_kind(db, job_id, "daily_search")
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    run = job_views.get_search_run_for_job(db, job)
    if not run:
        raise HTTPException(status_code=404, detail="Search run not found")
    if cursor is not None:
        try:
            job_views.decode_cursor(cursor)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid cursor") from exc
    all_matches = job_views.list_matches_for_run_ordered(db, run.id)
    matches = job_views.apply_cursor(all_matches, cursor)
    next_cursor = cursor
    if matches:
        latest = matches[-1]
        next_cursor = job_views.encode_cursor(latest.created_at, latest.id)
    return DailySearchJob(
        job=job_views.serialize_daily_search_job(db, job, run),
        subject=run.to_pydantic(job_id=job.id),
        items=[job_views.paper_match_response(db, match) for match in matches],
        next_cursor=next_cursor,
        done=job_views.is_done(job),
    )


@router.get(
    "/daily-search-summary/{job_id}",
    response_model=DailySearchSummaryJob,
)
def get_daily_search_summary_job(job_id: str, db: Session = Depends(get_db)):
    job = job_views.get_job_of_kind(db, job_id, "daily_search_summary")
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    run = job_views.get_search_run_for_job(db, job)
    if not run:
        raise HTTPException(status_code=404, detail="Search run not found")
    return DailySearchSummaryJob(
        job=job.to_pydantic(),
        run=search_run_payload(db, run),
        summary=summary_payload(run),
        done=job_views.is_done(job),
    )


@router.get("/idea-map/{job_id}", response_model=IdeaMapJob)
def get_idea_map_job(job_id: str, db: Session = Depends(get_db)):
    job = job_views.get_job_of_kind(db, job_id, "idea_map")
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    idea_map = job_views.get_idea_map_for_job(db, job)
    if not idea_map:
        raise HTTPException(status_code=404, detail="Idea map not found")
    return IdeaMapJob(
        job=job_views.serialize_idea_map_job(db, job, idea_map),
        subject=idea_map.to_pydantic(job_id=job.id),
        items=[],
        next_cursor=None,
        done=job_views.is_done(job),
    )


@router.get(
    "/onboarding-generation/{job_id}",
    response_model=OnboardingGenerationJob,
)
def get_onboarding_generation_job(
    job_id: str,
    cursor: str | None = None,
    db: Session = Depends(get_db),
):
    job = job_views.get_job_of_kind(db, job_id, "onboarding_generation")
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if cursor is not None:
        try:
            job_views.decode_cursor(cursor)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid cursor") from exc
    all_filters = job_views.draft_filters_for_generation(db, job.id)
    filters = job_views.apply_cursor(all_filters, cursor)
    next_cursor = cursor
    if filters:
        latest = filters[-1]
        next_cursor = job_views.encode_cursor(latest.created_at, latest.id)
    return OnboardingGenerationJob(
        job=job_views.serialize_onboarding_generation_job(db, job),
        subject=job.to_pydantic(),
        items=[item.to_pydantic() for item in filters],
        next_cursor=next_cursor,
        done=job_views.is_done(job),
    )


@router.get(
    "/onboarding-extraction/{job_id}",
    response_model=OnboardingExtractionJob,
)
def get_onboarding_extraction_job(job_id: str, db: Session = Depends(get_db)):
    job = job_views.get_job_of_kind(db, job_id, "onboarding_extraction")
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    extraction = job_views.get_extraction_for_job(db, job)
    if not extraction:
        raise HTTPException(status_code=404, detail="Extraction not found")
    return OnboardingExtractionJob(
        job=job_views.serialize_onboarding_extraction_job(db, job, extraction),
        subject=extraction.to_pydantic(job_id=job.id),
        items=[],
        next_cursor=None,
        done=job_views.is_done(job),
    )


@router.get(
    "/document-processing/{job_id}",
    response_model=DocumentProcessingJob,
)
def get_document_processing_job(job_id: str, db: Session = Depends(get_db)):
    job = job_views.get_job_of_kind(db, job_id, "document_processing")
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    document = job_views.get_document_for_job(db, job)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentProcessingJob(
        job=job_views.serialize_document_job(job, document),
        subject=document.to_pydantic(job_id=job.id),
        items=[],
        next_cursor=None,
        done=job_views.is_done(job),
    )
