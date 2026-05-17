import uuid
import threading
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
from app.jobs.queue import get_queue
from app.jobs.onboarding import extract_onboarding_filters

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.get("/status", response_model=OnboardingStatusResponse)
def get_onboarding_status(db: Session = Depends(get_db)):
    active_count = db.query(Filter).filter(Filter.status == "active").count()
    return OnboardingStatusResponse(
        completed=active_count > 0,
        active_filter_count=active_count,
    )


@router.post("/extractions", response_model=OnboardingExtractionResponse)
def create_extraction(body: OnboardingExtractionCreate, db: Session = Depends(get_db)):
    extraction = OnboardingExtraction(
        id=str(uuid.uuid4()),
        input_text=body.input_text,
        status="queued",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(extraction)
    db.commit()
    db.refresh(extraction)

    try:
        q = get_queue()
        q.enqueue(extract_onboarding_filters, extraction.id)
    except Exception:
        threading.Thread(
            target=extract_onboarding_filters,
            args=(extraction.id,),
            daemon=True,
        ).start()

    return extraction


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
