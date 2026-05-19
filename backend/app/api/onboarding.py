from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.http_errors import raise_http_from_service
from app.core.config import settings
from app.db.session import get_db
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
from app.services import onboarding as onboarding_service

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.get("/status", response_model=OnboardingStatusResponse)
def get_onboarding_status(db: Session = Depends(get_db)):
    completed, active_count = onboarding_service.onboarding_status(db)
    return OnboardingStatusResponse(
        completed=completed,
        active_filter_count=active_count,
    )


@router.post("/generations", response_model=JobStartResponse)
def create_generation(body: OnboardingGenerationCreate, db: Session = Depends(get_db)):
    try:
        job_id = onboarding_service.start_generation(db, body)
    except Exception as exc:
        raise_http_from_service(exc)
    return JobStartResponse(job_id=job_id)


@router.post("/draft-filters/promote", response_model=list[FilterResponse])
def promote_draft_filters(body: DraftFilterPromoteRequest, db: Session = Depends(get_db)):
    try:
        filters = onboarding_service.promote_draft_filters(db, body.filter_ids)
    except Exception as exc:
        raise_http_from_service(exc)
    return [filt.to_pydantic() for filt in filters]


@router.post("/extractions", response_model=JobStartResponse)
def create_extraction(body: OnboardingExtractionCreate, db: Session = Depends(get_db)):
    if len(body.input_text) > settings.ONBOARDING_INPUT_MAX_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"Input text must be {settings.ONBOARDING_INPUT_MAX_CHARS} characters or fewer",
        )
    try:
        job_id = onboarding_service.start_extraction(db, input_text=body.input_text)
    except Exception as exc:
        raise_http_from_service(exc)
    return JobStartResponse(job_id=job_id)


@router.get("/extractions/{extraction_id}", response_model=OnboardingExtractionResponse)
def get_extraction(extraction_id: str, db: Session = Depends(get_db)):
    try:
        extraction = onboarding_service.get_extraction(db, extraction_id)
    except Exception as exc:
        raise_http_from_service(exc)
    return onboarding_service.extraction_payload(db, extraction)


@router.post("/complete", response_model=list[FilterResponse])
def complete_onboarding(body: OnboardingCompleteRequest, db: Session = Depends(get_db)):
    filters = onboarding_service.complete_onboarding(db, body)
    return [filt.to_pydantic() for filt in filters]
