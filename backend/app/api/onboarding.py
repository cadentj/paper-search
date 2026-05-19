import uuid
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.filter import Filter
from app.models.onboarding_extraction import OnboardingExtraction
from app.schemas.onboarding import (
    OnboardingStatusResponse,
    OnboardingExtractionCreate,
    OnboardingExtractionResponse,
    OnboardingCompleteRequest,
    OnboardingGenerationCreate,
    DraftFilterPromoteRequest,
)
from app.schemas.filters import FilterResponse
from app.schemas.jobs import JobStartResponse
from app.jobs.queue import get_queue
from app.jobs.onboarding import extract_onboarding_filters, generate_onboarding_draft_filters
from app.services.jobs import create_job, latest_job_for_subject

router = APIRouter(prefix="/onboarding", tags=["onboarding"])
logger = logging.getLogger(__name__)


@router.get("/status", response_model=OnboardingStatusResponse)
def get_onboarding_status(db: Session = Depends(get_db)):
    active_count = db.query(Filter).filter(Filter.status == "active").count()
    return OnboardingStatusResponse(
        completed=active_count > 0,
        active_filter_count=active_count,
    )


@router.post("/generations", response_model=JobStartResponse)
def create_generation(body: OnboardingGenerationCreate, db: Session = Depends(get_db)):
    input_text = body.input_text.strip()
    if len(input_text) > settings.ONBOARDING_INPUT_MAX_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"Input text must be {settings.ONBOARDING_INPUT_MAX_CHARS} characters or fewer",
        )
    if not input_text and not body.document_ids:
        raise HTTPException(status_code=400, detail="Add text or at least one document")

    job_record = create_job(
        db,
        kind="onboarding_generation",
        subject_type="onboarding_generation",
        status="queued",
    )
    db.flush()
    job_record.subject_id = job_record.id
    db.commit()
    db.refresh(job_record)

    try:
        q = get_queue()
        job = q.enqueue(
            generate_onboarding_draft_filters,
            input_text,
            body.document_ids,
            job_record.id,
        )
        job_record.queue_job_id = getattr(job, "id", None)
        db.commit()
    except Exception as exc:
        logger.exception("failed to enqueue onboarding generation=%s", job_record.id)
        now = datetime.now(timezone.utc)
        job_record.status = "failed"
        job_record.error = f"Could not enqueue onboarding generation: {exc}"
        job_record.completed_at = now
        db.commit()
        raise HTTPException(status_code=503, detail=job_record.error) from exc

    return JobStartResponse(job_id=job_record.id)


@router.post("/draft-filters/promote", response_model=list[FilterResponse])
def promote_draft_filters(
    body: DraftFilterPromoteRequest,
    db: Session = Depends(get_db),
):
    if not body.filter_ids:
        return []

    now = datetime.now(timezone.utc)
    filters = db.query(Filter).filter(Filter.id.in_(body.filter_ids)).all()
    by_id = {f.id: f for f in filters}
    ordered_filters = [by_id[fid] for fid in body.filter_ids if fid in by_id]
    missing = [fid for fid in body.filter_ids if fid not in by_id]
    if missing:
        raise HTTPException(status_code=404, detail=f"Draft filter not found: {missing[0]}")

    for filt in ordered_filters:
        if filt.status != "draft":
            raise HTTPException(status_code=400, detail=f"Filter is not a draft: {filt.id}")
        filt.status = "active"
        filt.updated_at = now

    db.commit()
    for filt in ordered_filters:
        db.refresh(filt)
    return [filt.to_pydantic() for filt in ordered_filters]


@router.post("/extractions", response_model=JobStartResponse)
def create_extraction(body: OnboardingExtractionCreate, db: Session = Depends(get_db)):
    extraction = OnboardingExtraction(
        id=str(uuid.uuid4()),
        input_text=body.input_text,
        status="queued",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(extraction)
    job_record = create_job(
        db,
        kind="onboarding_extraction",
        subject_type="onboarding_extraction",
        subject_id=extraction.id,
        status="queued",
    )
    db.commit()
    db.refresh(extraction)
    db.refresh(job_record)

    try:
        q = get_queue()
        job = q.enqueue(extract_onboarding_filters, extraction.id, job_record.id)
        job_record.queue_job_id = getattr(job, "id", None)
        db.commit()
        logger.info(
            "enqueued onboarding extraction=%s job=%s",
            extraction.id,
            getattr(job, "id", None),
        )
    except Exception as exc:
        logger.exception("failed to enqueue onboarding extraction=%s", extraction.id)
        extraction.status = "failed"
        extraction.error = f"Could not enqueue onboarding extraction: {exc}"
        extraction.updated_at = datetime.now(timezone.utc)
        job_record.status = "failed"
        job_record.error = extraction.error
        job_record.completed_at = extraction.updated_at
        db.commit()
        raise HTTPException(status_code=503, detail=extraction.error) from exc

    return JobStartResponse(job_id=job_record.id)


@router.get("/extractions/{extraction_id}", response_model=OnboardingExtractionResponse)
def get_extraction(extraction_id: str, db: Session = Depends(get_db)):
    extraction = db.query(OnboardingExtraction).filter(
        OnboardingExtraction.id == extraction_id
    ).first()
    if not extraction:
        raise HTTPException(status_code=404, detail="Extraction not found")
    return _extraction_payload(extraction, db)


@router.post("/complete", response_model=list[FilterResponse])
def complete_onboarding(body: OnboardingCompleteRequest, db: Session = Depends(get_db)):
    created_filters = []
    now = datetime.now(timezone.utc)

    for f_data in body.filters:
        definition = f_data.get("definition", f_data)
        name = definition.get("name", f_data.get("name", "Unnamed Filter"))
        definition = {
            "name": name,
            "description": definition.get("description", ""),
            "mode": definition.get("mode", "topic"),
        }

        filt = Filter(
            id=str(uuid.uuid4()),
            name=name,
            definition=definition,
            status="active",
            created_at=now,
            updated_at=now,
        )
        db.add(filt)
        created_filters.append(filt)

    db.commit()
    for f in created_filters:
        db.refresh(f)

    return [filt.to_pydantic() for filt in created_filters]


def _extraction_payload(extraction: OnboardingExtraction, db: Session) -> OnboardingExtractionResponse:
    job = latest_job_for_subject(
        db,
        subject_type="onboarding_extraction",
        subject_id=extraction.id,
        kind="onboarding_extraction",
    )
    return extraction.to_pydantic(job_id=job.id if job else None)
