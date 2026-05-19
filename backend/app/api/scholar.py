from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.http_errors import raise_http_from_service
from app.db.session import get_db
from app.services.semantic_scholar import extract_author_id, get_author
from app.services import scholar as scholar_service

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
        raise HTTPException(
            status_code=400,
            detail="Could not parse Semantic Scholar author ID from URL",
        )

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
    try:
        import_id, job_id = scholar_service.start_profile_import(
            db,
            url=body.url,
            author_id=body.author_id,
            display_name=body.display_name,
        )
    except Exception as exc:
        raise_http_from_service(exc)
    return ImportResponse(id=import_id, job_id=job_id)


@router.get("/imports/{import_id}", response_model=ImportStatusResponse)
def get_import_status(import_id: str, db: Session = Depends(get_db)):
    try:
        profile_import = scholar_service.get_import(db, import_id)
    except Exception as exc:
        raise_http_from_service(exc)
    return ImportStatusResponse(
        id=profile_import.id,
        status=profile_import.status,
        display_name=profile_import.display_name,
        error=profile_import.error,
    )
