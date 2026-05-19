from datetime import date, datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.http_errors import raise_http_from_service
from app.db.session import get_db
from app.models.idea_map import IdeaMap
from paper_search_core.models.paper import Paper
from app.api.jobs import JobStart
from app.services.sources import KNOWN_SOURCE_TYPES, paper_html
from app.services import papers as papers_service

router = APIRouter(prefix="/papers", tags=["papers"])


class PaginatedPapers(BaseModel):
    papers: list[Paper]
    total: int
    page: int
    per_page: int


class PaperNote(BaseModel):
    id: str
    paper_id: str
    text: str
    created_at: datetime
    updated_at: datetime


class PaperNoteUpdate(BaseModel):
    text: str


@router.get("/daily", response_model=PaginatedPapers)
def get_daily_papers(
    run_date: date,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    papers, total = papers_service.list_papers_for_date(
        db, run_date, page=page, per_page=per_page
    )
    return PaginatedPapers(
        papers=[p.to_pydantic() for p in papers],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/{paper_id}", response_model=Paper)
def get_paper(paper_id: str, db: Session = Depends(get_db)):
    try:
        paper = papers_service.get_paper(db, paper_id)
    except Exception as exc:
        raise_http_from_service(exc)
    return paper.to_pydantic()


@router.get("/{paper_id}/html")
def get_paper_html(paper_id: str, db: Session = Depends(get_db)):
    try:
        paper = papers_service.get_paper(db, paper_id)
    except Exception as exc:
        raise_http_from_service(exc)
    if (paper.source_type or "arxiv") not in KNOWN_SOURCE_TYPES:
        return {"html": None, "source_url": paper.source_url}
    return paper_html(paper)


@router.post("/{paper_id}/idea-map", response_model=JobStart)
def create_or_get_idea_map(paper_id: str, db: Session = Depends(get_db)):
    try:
        job_id = papers_service.start_idea_map(db, paper_id)
    except Exception as exc:
        raise_http_from_service(exc)
    return JobStart(job_id=job_id)


@router.get("/{paper_id}/notes", response_model=PaperNote | None)
def get_paper_notes(paper_id: str, db: Session = Depends(get_db)):
    try:
        note = papers_service.get_paper_note(db, paper_id)
    except Exception as exc:
        raise_http_from_service(exc)
    if not note:
        return None
    return PaperNote(
        id=note.id,
        paper_id=note.paper_id,
        text=note.text,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


@router.put("/{paper_id}/notes", response_model=PaperNote)
def update_paper_notes(
    paper_id: str, body: PaperNoteUpdate, db: Session = Depends(get_db)
):
    note = papers_service.upsert_paper_note(db, paper_id, body.text)
    return PaperNote(
        id=note.id,
        paper_id=note.paper_id,
        text=note.text,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


@router.get("/{paper_id}/idea-map", response_model=IdeaMap)
def get_idea_map(paper_id: str, db: Session = Depends(get_db)):
    try:
        idea_map = papers_service.get_idea_map_for_paper(db, paper_id)
    except Exception as exc:
        raise_http_from_service(exc)
    return papers_service.idea_map_payload(db, idea_map)
