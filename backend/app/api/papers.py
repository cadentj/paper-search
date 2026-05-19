import uuid
import logging
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from pydantic import BaseModel

from app.db.session import get_db
from app.models.paper import Paper
from app.models.paper_note import PaperNote
from app.models.idea_map import IdeaMap
from app.schemas.papers import PaperResponse, IdeaMapResponse
from app.schemas.jobs import JobStartResponse
from app.jobs.queue import get_queue
from app.jobs.idea_map import generate_idea_map
from app.services.jobs import create_job, latest_job_for_subject
from app.services.source_providers import provider_for

router = APIRouter(prefix="/papers", tags=["papers"])
logger = logging.getLogger(__name__)


class PaginatedPapersResponse(BaseModel):
    papers: list[PaperResponse]
    total: int
    page: int
    per_page: int


@router.get("/daily", response_model=PaginatedPapersResponse)
def get_daily_papers(
    run_date: date,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(Paper).filter(
        func.date(Paper.published_at) == run_date
    )
    total = query.count()
    papers = (
        query
        .order_by(Paper.title)
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return PaginatedPapersResponse(
        papers=[p.to_pydantic() for p in papers],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/{paper_id}", response_model=PaperResponse)
def get_paper(paper_id: str, db: Session = Depends(get_db)):
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper.to_pydantic()


@router.get("/{paper_id}/html")
def get_paper_html(paper_id: str, db: Session = Depends(get_db)):
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    provider = provider_for(paper.source_type or "arxiv")
    if not provider:
        return {"html": None, "source_url": paper.source_url}
    return provider.html_for_paper(paper)


@router.post("/{paper_id}/idea-map", response_model=JobStartResponse)
def create_or_get_idea_map(paper_id: str, db: Session = Depends(get_db)):
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    existing = db.query(IdeaMap).filter(IdeaMap.paper_id == paper_id).first()
    if existing:
        if existing.status in {"queued", "running", "claims_running", "warrants_running"}:
            job = latest_job_for_subject(
                db,
                subject_type="idea_map",
                subject_id=existing.id,
                kind="idea_map",
            )
            if not job:
                job = create_job(
                    db,
                    kind="idea_map",
                    subject_type="idea_map",
                    subject_id=existing.id,
                    status=existing.status,
                )
                db.commit()
                db.refresh(job)
            return JobStartResponse(job_id=job.id)

        existing.status = "queued"
        existing.claims = []
        existing.dropped_reason = None
        existing.error = None
        existing.updated_at = datetime.now(timezone.utc)
        job_record = create_job(
            db,
            kind="idea_map",
            subject_type="idea_map",
            subject_id=existing.id,
            status="queued",
        )
        db.commit()
        db.refresh(existing)
        db.refresh(job_record)
        return _enqueue_idea_map(existing, db, job_record)

    now = datetime.now(timezone.utc)
    idea_map = IdeaMap(
        id=str(uuid.uuid4()),
        paper_id=paper_id,
        status="queued",
        created_at=now,
        updated_at=now,
    )
    db.add(idea_map)
    job_record = create_job(
        db,
        kind="idea_map",
        subject_type="idea_map",
        subject_id=idea_map.id,
        status="queued",
    )
    db.commit()
    db.refresh(idea_map)
    db.refresh(job_record)

    return _enqueue_idea_map(idea_map, db, job_record)


def _enqueue_idea_map(idea_map: IdeaMap, db: Session, job_record) -> JobStartResponse:
    try:
        q = get_queue()
        job = q.enqueue(generate_idea_map, idea_map.id, job_record.id)
        job_record.queue_job_id = getattr(job, "id", None)
        db.commit()
        logger.info("enqueued idea map=%s job=%s", idea_map.id, getattr(job, "id", None))
    except Exception as exc:
        logger.exception("failed to enqueue idea map=%s", idea_map.id)
        idea_map.status = "failed"
        idea_map.error = f"Could not enqueue idea map generation: {exc}"
        idea_map.updated_at = datetime.now(timezone.utc)
        job_record.status = "failed"
        job_record.error = idea_map.error
        job_record.completed_at = idea_map.updated_at
        db.commit()
        raise HTTPException(status_code=503, detail=idea_map.error) from exc

    return JobStartResponse(job_id=job_record.id)


class PaperNoteResponse(BaseModel):
    id: str
    paper_id: str
    text: str
    created_at: datetime
    updated_at: datetime


class PaperNoteUpdate(BaseModel):
    text: str


@router.get("/{paper_id}/notes", response_model=PaperNoteResponse | None)
def get_paper_notes(paper_id: str, db: Session = Depends(get_db)):
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    note = db.query(PaperNote).filter(PaperNote.paper_id == paper_id).first()
    if not note:
        return None
    return PaperNoteResponse(
        id=note.id, paper_id=note.paper_id, text=note.text,
        created_at=note.created_at, updated_at=note.updated_at,
    )


@router.put("/{paper_id}/notes", response_model=PaperNoteResponse)
def update_paper_notes(paper_id: str, body: PaperNoteUpdate, db: Session = Depends(get_db)):
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    now = datetime.now(timezone.utc)
    note = db.query(PaperNote).filter(PaperNote.paper_id == paper_id).first()
    if note:
        note.text = body.text
        note.updated_at = now
    else:
        note = PaperNote(
            id=str(uuid.uuid4()),
            paper_id=paper_id,
            text=body.text,
            created_at=now,
            updated_at=now,
        )
        db.add(note)
    db.flush()
    db.refresh(note)
    return PaperNoteResponse(
        id=note.id, paper_id=note.paper_id, text=note.text,
        created_at=note.created_at, updated_at=note.updated_at,
    )


@router.get("/{paper_id}/idea-map", response_model=IdeaMapResponse)
def get_idea_map(paper_id: str, db: Session = Depends(get_db)):
    idea_map = db.query(IdeaMap).filter(IdeaMap.paper_id == paper_id).first()
    if not idea_map:
        raise HTTPException(status_code=404, detail="Idea map not found")
    return _idea_map_payload(idea_map, db)


def _idea_map_payload(idea_map: IdeaMap, db: Session) -> IdeaMapResponse:
    job = latest_job_for_subject(
        db,
        subject_type="idea_map",
        subject_id=idea_map.id,
        kind="idea_map",
    )
    return idea_map.to_pydantic(job_id=job.id if job else None)
