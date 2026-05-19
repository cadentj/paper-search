from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.http_errors import raise_http_from_service
from app.api.jobs import JobStart
from app.config import settings
from app.db.session import get_db
from app.models.filter import Filter
from app.models.onboarding_extraction import OnboardingExtraction
from app.services import onboarding as onboarding_service
from app.services.semantic_scholar import extract_author_id, get_author

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


class OnboardingStatus(BaseModel):
    completed: bool
    active_filter_count: int


class OnboardingExtractionCreate(BaseModel):
    input_text: str


class OnboardingCompleteRequest(BaseModel):
    filters: list[dict]


class OnboardingGenerationCreate(BaseModel):
    input_text: str
    document_ids: list[str] = []


class DraftFilterPromoteRequest(BaseModel):
    filter_ids: list[str]


class ScholarVerifyRequest(BaseModel):
    url: str


class ScholarVerify(BaseModel):
    author_id: str
    name: str
    affiliations: list[str]
    paper_count: int | None = None
    h_index: int | None = None


class ScholarImportRequest(BaseModel):
    url: str
    author_id: str
    display_name: str


class ScholarImport(BaseModel):
    id: str
    job_id: str


class ScholarImportStatus(BaseModel):
    id: str
    status: str
    display_name: Optional[str] = None
    error: Optional[str] = None


@router.get("/status", response_model=OnboardingStatus)
def get_onboarding_status(db: Session = Depends(get_db)):
    completed, active_count = onboarding_service.onboarding_status(db)
    return OnboardingStatus(
        completed=completed,
        active_filter_count=active_count,
    )


@router.post("/generations", response_model=JobStart)
def create_generation(body: OnboardingGenerationCreate, db: Session = Depends(get_db)):
    try:
        job_id = onboarding_service.start_generation(db, body)
    except Exception as exc:
        raise_http_from_service(exc)
    return JobStart(job_id=job_id)


@router.post("/draft-filters/promote", response_model=list[Filter])
def promote_draft_filters(
    body: DraftFilterPromoteRequest, db: Session = Depends(get_db)
):
    try:
        filters = onboarding_service.promote_draft_filters(db, body.filter_ids)
    except Exception as exc:
        raise_http_from_service(exc)
    return [filter.to_pydantic() for filter in filters]


@router.post("/extractions", response_model=JobStart)
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
    return JobStart(job_id=job_id)


@router.get("/extractions/{extraction_id}", response_model=OnboardingExtraction)
def get_extraction(extraction_id: str, db: Session = Depends(get_db)):
    try:
        extraction = onboarding_service.get_extraction(db, extraction_id)
    except Exception as exc:
        raise_http_from_service(exc)
    return onboarding_service.extraction_payload(db, extraction)


@router.post("/complete", response_model=list[Filter])
def complete_onboarding(body: OnboardingCompleteRequest, db: Session = Depends(get_db)):
    filters = onboarding_service.complete_onboarding(db, body)
    return [filter.to_pydantic() for filter in filters]


@router.post("/scholar/verify", response_model=ScholarVerify)
def verify_profile(body: ScholarVerifyRequest):
    author_id = extract_author_id(body.url)
    if not author_id:
        raise HTTPException(
            status_code=400,
            detail="Could not parse Semantic Scholar author ID from URL",
        )

    author = get_author(author_id)
    if not author:
        raise HTTPException(
            status_code=404, detail="Author not found on Semantic Scholar"
        )

    return ScholarVerify(
        author_id=author_id,
        name=author.get("name", ""),
        affiliations=author.get("affiliations") or [],
        paper_count=author.get("paperCount"),
        h_index=author.get("hIndex"),
    )


@router.post("/scholar/imports", response_model=ScholarImport)
def start_import(body: ScholarImportRequest, db: Session = Depends(get_db)):
    try:
        import_id, job_id = onboarding_service.start_profile_import(
            db,
            url=body.url,
            author_id=body.author_id,
            display_name=body.display_name,
        )
    except Exception as exc:
        raise_http_from_service(exc)
    return ScholarImport(id=import_id, job_id=job_id)


@router.get("/scholar/imports/{import_id}", response_model=ScholarImportStatus)
def get_import_status(import_id: str, db: Session = Depends(get_db)):
    try:
        profile_import = onboarding_service.get_import(db, import_id)
    except Exception as exc:
        raise_http_from_service(exc)
    return ScholarImportStatus(
        id=profile_import.id,
        status=profile_import.status,
        display_name=profile_import.display_name,
        error=profile_import.error,
    )
