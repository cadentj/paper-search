import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db
from app.models.research_profile_import import ResearchProfileImport
from app.schemas.jobs import JobStartResponse
from app.services.jobs import create_job
from app.services.semantic_scholar import extract_author_id, get_author
from app.jobs.queue import get_queue
from app.jobs.scholar_import import run_scholar_import

router = APIRouter(prefix="/onboarding/scholar", tags=["scholar"])


class VerifyRequest(BaseModel):
    url: str


class VerifyResponse(BaseModel):
    author_id: str
    name: str
    affiliations: list[str]
    paper_count: int | None = None
    h_index: int | None = None


class ImportRequest(BaseModel):
    url: str
    author_id: str
    display_name: str


class ImportResponse(BaseModel):
    id: str
    job_id: str


class ImportStatusResponse(BaseModel):
    id: str
    status: str
    display_name: Optional[str] = None
    error: Optional[str] = None


@router.post("/verify", response_model=VerifyResponse)
def verify_profile(body: VerifyRequest):
    author_id = extract_author_id(body.url)
    if not author_id:
        raise HTTPException(status_code=400, detail="Could not parse Semantic Scholar author ID from URL")

    author = get_author(author_id)
    if not author:
        raise HTTPException(status_code=404, detail="Author not found on Semantic Scholar")

    return VerifyResponse(
        author_id=author_id,
        name=author.get("name", ""),
        affiliations=author.get("affiliations") or [],
        paper_count=author.get("paperCount"),
        h_index=author.get("hIndex"),
    )


@router.post("/imports", response_model=ImportResponse)
def start_import(body: ImportRequest, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    profile_import = ResearchProfileImport(
        id=str(uuid.uuid4()),
        status="pending",
        source_type="semantic_scholar",
        source_url=body.url,
        external_author_id=body.author_id,
        display_name=body.display_name,
        created_at=now,
        updated_at=now,
    )
    db.add(profile_import)

    job_record = create_job(
        db,
        kind="scholar_import",
        subject_type="research_profile_import",
        subject_id=profile_import.id,
    )
    db.commit()

    try:
        q = get_queue()
        q.enqueue(run_scholar_import, profile_import.id, job_record.id)
    except Exception as exc:
        profile_import.status = "failed"
        profile_import.error = str(exc)
        job_record.status = "failed"
        job_record.error = str(exc)
        job_record.completed_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return ImportResponse(id=profile_import.id, job_id=job_record.id)


@router.get("/imports/{import_id}", response_model=ImportStatusResponse)
def get_import_status(import_id: str, db: Session = Depends(get_db)):
    profile_import = db.query(ResearchProfileImport).filter(
        ResearchProfileImport.id == import_id
    ).first()
    if not profile_import:
        raise HTTPException(status_code=404, detail="Import not found")
    return ImportStatusResponse(
        id=profile_import.id,
        status=profile_import.status,
        display_name=profile_import.display_name,
        error=profile_import.error,
    )
