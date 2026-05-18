import base64
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.document import Document
from app.models.filter import Filter
from app.models.idea_map import IdeaMap
from app.models.job import Job
from app.models.onboarding_extraction import OnboardingExtraction
from app.models.paper import Paper
from app.models.paper_match import PaperMatch
from app.models.search_run import SearchRun
from app.schemas.jobs import (
    DailySearchJobResponse,
    DocumentProcessingJobResponse,
    IdeaMapJobResponse,
    JobResponse,
    OnboardingExtractionJobResponse,
    OnboardingGenerationJobResponse,
)
from app.schemas.search import PaperMatchResponse


router = APIRouter(prefix="/jobs", tags=["jobs"])
DONE_STATUSES = {"completed", "failed"}


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_pydantic()


def _get_job(db: Session, job_id: str, kind: str) -> Job:
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.kind != kind:
        raise HTTPException(status_code=400, detail=f"Job is not a {kind} job")
    return job


def _is_done(job: Job) -> bool:
    return job.status in DONE_STATUSES


def _serialize_job(job: Job) -> JobResponse:
    return job.to_pydantic()


def _encode_cursor(value: datetime, item_id: str) -> str:
    payload = {"at": value.isoformat(), "id": item_id}
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str | None) -> tuple[datetime, str] | None:
    if not cursor:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
        value = datetime.fromisoformat(payload["at"])
        if value.tzinfo is not None:
            value = value.replace(tzinfo=None)
        return value, str(payload["id"])
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid cursor") from exc


def _apply_cursor(query, model, column, cursor: str | None):
    decoded = _decode_cursor(cursor)
    if not decoded:
        return query
    value, item_id = decoded
    return query.filter(or_(column > value, and_(column == value, model.id > item_id)))


def _paper_match_response(db: Session, match: PaperMatch) -> PaperMatchResponse:
    paper = db.query(Paper).filter(Paper.id == match.paper_id).first()
    filt = db.query(Filter).filter(Filter.id == match.filter_id).first()
    return match.to_pydantic(paper=paper, filt=filt)


@router.get("/daily-search/{job_id}", response_model=DailySearchJobResponse)
def get_daily_search_job(
    job_id: str,
    cursor: str | None = None,
    db: Session = Depends(get_db),
):
    job = _get_job(db, job_id, "daily_search")
    run = db.query(SearchRun).filter(SearchRun.id == job.subject_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Search run not found")

    query = db.query(PaperMatch).filter(PaperMatch.search_run_id == run.id)
    matches = (
        _apply_cursor(query, PaperMatch, PaperMatch.created_at, cursor)
        .order_by(PaperMatch.created_at.asc(), PaperMatch.id.asc())
        .all()
    )
    next_cursor = cursor
    if matches:
        latest = matches[-1]
        next_cursor = _encode_cursor(latest.created_at, latest.id)

    return DailySearchJobResponse(
        job=_serialize_job(job),
        subject=run.to_pydantic(job_id=job.id),
        items=[_paper_match_response(db, match) for match in matches],
        next_cursor=next_cursor,
        done=_is_done(job),
    )


@router.get("/idea-map/{job_id}", response_model=IdeaMapJobResponse)
def get_idea_map_job(job_id: str, db: Session = Depends(get_db)):
    job = _get_job(db, job_id, "idea_map")
    idea_map = db.query(IdeaMap).filter(IdeaMap.id == job.subject_id).first()
    if not idea_map:
        raise HTTPException(status_code=404, detail="Idea map not found")
    return IdeaMapJobResponse(
        job=_serialize_job(job),
        subject=idea_map.to_pydantic(job_id=job.id),
        items=[],
        next_cursor=None,
        done=_is_done(job),
    )


@router.get(
    "/onboarding-generation/{job_id}",
    response_model=OnboardingGenerationJobResponse,
)
def get_onboarding_generation_job(
    job_id: str,
    cursor: str | None = None,
    db: Session = Depends(get_db),
):
    job = _get_job(db, job_id, "onboarding_generation")
    filter_ids = (job.progress or {}).get("filter_ids") or []
    query = (
        db.query(Filter).filter(Filter.id.in_(filter_ids))
        if filter_ids
        else db.query(Filter).filter(Filter.id == "__no_filters__")
    )
    filters = (
        _apply_cursor(query, Filter, Filter.created_at, cursor)
        .order_by(Filter.created_at.asc(), Filter.id.asc())
        .all()
    )
    next_cursor = cursor
    if filters:
        latest = filters[-1]
        next_cursor = _encode_cursor(latest.created_at, latest.id)
    return OnboardingGenerationJobResponse(
        job=_serialize_job(job),
        subject=_serialize_job(job),
        items=[item.to_pydantic() for item in filters],
        next_cursor=next_cursor,
        done=_is_done(job),
    )


@router.get(
    "/onboarding-extraction/{job_id}",
    response_model=OnboardingExtractionJobResponse,
)
def get_onboarding_extraction_job(job_id: str, db: Session = Depends(get_db)):
    job = _get_job(db, job_id, "onboarding_extraction")
    extraction = db.query(OnboardingExtraction).filter(
        OnboardingExtraction.id == job.subject_id
    ).first()
    if not extraction:
        raise HTTPException(status_code=404, detail="Extraction not found")
    return OnboardingExtractionJobResponse(
        job=_serialize_job(job),
        subject=extraction.to_pydantic(job_id=job.id),
        items=[],
        next_cursor=None,
        done=_is_done(job),
    )


@router.get(
    "/document-processing/{job_id}",
    response_model=DocumentProcessingJobResponse,
)
def get_document_processing_job(job_id: str, db: Session = Depends(get_db)):
    job = _get_job(db, job_id, "document_processing")
    document = db.query(Document).filter(Document.id == job.subject_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentProcessingJobResponse(
        job=_serialize_job(job),
        subject=document.to_pydantic(job_id=job.id),
        items=[],
        next_cursor=None,
        done=_is_done(job),
    )
