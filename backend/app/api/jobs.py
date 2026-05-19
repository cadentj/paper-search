from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.http_errors import raise_http_from_service
from app.db.session import get_db
from app.models.document import Document
from app.models.filter import Filter
from app.models.idea_map import IdeaMap
from app.models.job import Job
from app.models.onboarding_extraction import OnboardingExtraction
from app.models.paper_match import PaperMatch
from app.models.search_run import SearchRun
from app.services import job_views
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
    summary: DailySearchSummary | None = None
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


@router.get("/{job_id}", response_model=Job)
def get_job(job_id: str, db: Session = Depends(get_db)):
    try:
        job = job_views.get_job(db, job_id)
    except Exception as exc:
        raise_http_from_service(exc)
    return job.to_pydantic()


@router.get("/daily-search/{job_id}", response_model=DailySearchJob)
def get_daily_search_job(
    job_id: str,
    cursor: str | None = None,
    db: Session = Depends(get_db),
):
    try:
        job = job_views.get_job_of_kind(db, job_id, "daily_search")
        run = job_views.get_search_run_for_job(db, job)
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
    except Exception as exc:
        raise_http_from_service(exc)


@router.get(
    "/daily-search-summary/{job_id}",
    response_model=DailySearchSummaryJob,
)
def get_daily_search_summary_job(job_id: str, db: Session = Depends(get_db)):
    try:
        job = job_views.get_job_of_kind(db, job_id, "daily_search_summary")
        run = job_views.get_search_run_for_job(db, job)
    except Exception as exc:
        raise_http_from_service(exc)
    return DailySearchSummaryJob(
        job=job.to_pydantic(),
        run=search_run_payload(db, run),
        summary=summary_payload(run),
        done=job_views.is_done(job),
    )


@router.get("/idea-map/{job_id}", response_model=IdeaMapJob)
def get_idea_map_job(job_id: str, db: Session = Depends(get_db)):
    try:
        job = job_views.get_job_of_kind(db, job_id, "idea_map")
        idea_map = job_views.get_idea_map_for_job(db, job)
    except Exception as exc:
        raise_http_from_service(exc)
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
    try:
        job = job_views.get_job_of_kind(db, job_id, "onboarding_generation")
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
    except Exception as exc:
        raise_http_from_service(exc)


@router.get(
    "/onboarding-extraction/{job_id}",
    response_model=OnboardingExtractionJob,
)
def get_onboarding_extraction_job(job_id: str, db: Session = Depends(get_db)):
    try:
        job = job_views.get_job_of_kind(db, job_id, "onboarding_extraction")
        extraction = job_views.get_extraction_for_job(db, job)
    except Exception as exc:
        raise_http_from_service(exc)
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
    try:
        job = job_views.get_job_of_kind(db, job_id, "document_processing")
        document = job_views.get_document_for_job(db, job)
    except Exception as exc:
        raise_http_from_service(exc)
    return DocumentProcessingJob(
        job=job_views.serialize_document_job(job, document),
        subject=document.to_pydantic(job_id=job.id),
        items=[],
        next_cursor=None,
        done=job_views.is_done(job),
    )
