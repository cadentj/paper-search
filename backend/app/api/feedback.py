import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.filter import Filter
from app.models.paper import Paper
from app.models.paper_match import PaperMatch
from app.models.paper_match_feedback import PaperMatchFeedback
from app.models.paper_note import PaperNote
from app.services.jobs import create_job
from app.jobs.queue import get_queue
from app.jobs.feedback_reflection import process_all_feedback

router = APIRouter(tags=["feedback"])


class MatchFeedbackRequest(BaseModel):
    value: str  # "up" or "down"


class PaperFeedbackRequest(BaseModel):
    paper_id: str
    value: str  # "up" only for unmatched papers


class FeedbackResponse(BaseModel):
    id: str
    paper_id: str
    value: str
    paper_match_id: Optional[str] = None
    created_at: datetime


class FeedbackStatusResponse(BaseModel):
    pending_votes: int
    pending_notes: int
    pending_proposals: int


@router.post("/paper-matches/{match_id}/feedback", response_model=FeedbackResponse)
def submit_match_feedback(match_id: str, body: MatchFeedbackRequest, db: Session = Depends(get_db)):
    if body.value not in ("up", "down"):
        raise HTTPException(status_code=400, detail="value must be 'up' or 'down'")

    match = db.query(PaperMatch).filter(PaperMatch.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    now = datetime.now(timezone.utc)
    existing = db.query(PaperMatchFeedback).filter(
        PaperMatchFeedback.paper_match_id == match_id
    ).first()

    if existing:
        existing.value = body.value
        existing.updated_at = now
        existing.processed = False
        feedback = existing
    else:
        feedback = PaperMatchFeedback(
            id=str(uuid.uuid4()),
            paper_match_id=match_id,
            search_run_id=match.search_run_id,
            filter_id=match.filter_id,
            paper_id=match.paper_id,
            value=body.value,
            created_at=now,
            updated_at=now,
        )
        db.add(feedback)

    db.flush()
    db.refresh(feedback)

    return FeedbackResponse(
        id=feedback.id,
        paper_id=feedback.paper_id,
        value=feedback.value,
        paper_match_id=feedback.paper_match_id,
        created_at=feedback.created_at,
    )


@router.post("/papers/{paper_id}/feedback", response_model=FeedbackResponse)
def submit_paper_feedback(paper_id: str, body: PaperFeedbackRequest, db: Session = Depends(get_db)):
    if body.value != "up":
        raise HTTPException(status_code=400, detail="Only 'up' is allowed for unmatched papers")

    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    now = datetime.now(timezone.utc)
    existing = db.query(PaperMatchFeedback).filter(
        PaperMatchFeedback.paper_id == paper_id,
        PaperMatchFeedback.paper_match_id.is_(None),
    ).first()

    if existing:
        existing.updated_at = now
        existing.processed = False
        feedback = existing
    else:
        feedback = PaperMatchFeedback(
            id=str(uuid.uuid4()),
            paper_id=paper_id,
            value="up",
            created_at=now,
            updated_at=now,
        )
        db.add(feedback)

    db.flush()
    db.refresh(feedback)

    return FeedbackResponse(
        id=feedback.id,
        paper_id=feedback.paper_id,
        value=feedback.value,
        created_at=feedback.created_at,
    )


@router.get("/feedback/status", response_model=FeedbackStatusResponse)
def get_feedback_status(db: Session = Depends(get_db)):
    pending_votes = (
        db.query(PaperMatchFeedback)
        .filter(PaperMatchFeedback.processed == False)
        .count()
    )
    pending_notes = (
        db.query(PaperNote)
        .filter(PaperNote.processed == False, PaperNote.text != "")
        .count()
    )
    pending_proposals = (
        db.query(Filter)
        .filter(Filter.status.in_(["pending_create", "pending_revision", "pending_deletion"]))
        .count()
    )
    return FeedbackStatusResponse(
        pending_votes=pending_votes,
        pending_notes=pending_notes,
        pending_proposals=pending_proposals,
    )


@router.post("/feedback/process")
def trigger_feedback_processing(db: Session = Depends(get_db)):
    pending_votes = (
        db.query(PaperMatchFeedback)
        .filter(PaperMatchFeedback.processed == False)
        .count()
    )
    pending_notes = (
        db.query(PaperNote)
        .filter(PaperNote.processed == False, PaperNote.text != "")
        .count()
    )
    if pending_votes == 0 and pending_notes == 0:
        raise HTTPException(status_code=400, detail="No pending feedback to process")

    job_record = create_job(
        db,
        kind="feedback_reflection",
        subject_type="feedback_batch",
        subject_id="batch",
    )
    db.commit()

    try:
        q = get_queue()
        q.enqueue(process_all_feedback, job_record.id)
    except Exception as exc:
        job_record.status = "failed"
        job_record.error = str(exc)
        job_record.completed_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return {"job_id": job_record.id}
