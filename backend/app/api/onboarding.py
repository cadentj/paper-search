import uuid
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.filter import Filter
from app.models.onboarding_extraction import OnboardingExtraction
from app.schemas.onboarding import (
    OnboardingStatusResponse,
    OnboardingExtractionCreate,
    OnboardingExtractionResponse,
    OnboardingCompleteRequest,
)
from app.schemas.filters import FilterResponse
from app.schemas.jobs import JobStartResponse
from app.jobs.queue import get_queue
from app.jobs.onboarding import extract_onboarding_filters
from app.services.jobs import build_progress, create_job

router = APIRouter(prefix="/onboarding", tags=["onboarding"])
logger = logging.getLogger(__name__)


@router.get("/status", response_model=OnboardingStatusResponse)
def get_onboarding_status(db: Session = Depends(get_db)):
    active_count = db.query(Filter).filter(Filter.status == "active").count()
    return OnboardingStatusResponse(
        completed=active_count > 0,
        active_filter_count=active_count,
    )


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
        progress=build_progress(
            stage="queued",
            current=0,
            total=1,
            message="Queued, waiting for worker",
        ),
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
        job_record.progress = build_progress(
            stage="failed",
            current=0,
            total=1,
            message="Could not enqueue onboarding extraction. Is Redis running?",
            log=(job_record.progress or {}).get("log", []),
        )
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
    return extraction


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

    return created_filters
