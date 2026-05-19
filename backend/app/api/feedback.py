from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import feedback as feedback_service

router = APIRouter(tags=["feedback"])


class MatchFeedbackRequest(BaseModel):
    value: str


class PaperFeedbackRequest(BaseModel):
    paper_id: str
    value: str


class Feedback(BaseModel):
    id: str
    paper_id: str
    value: str
    paper_match_id: Optional[str] = None
    created_at: datetime


class FeedbackStatus(BaseModel):
    pending_votes: int
    pending_notes: int
    pending_proposals: int


@router.post("/paper-matches/{match_id}/feedback", response_model=Feedback)
def submit_match_feedback(
    match_id: str, body: MatchFeedbackRequest, db: Session = Depends(get_db)
):
    try:
        feedback = feedback_service.upsert_match_feedback(db, match_id, body.value)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Feedback(
        id=feedback.id,
        paper_id=feedback.paper_id,
        value=feedback.value,
        paper_match_id=feedback.paper_match_id,
        created_at=feedback.created_at,
    )


@router.post("/papers/{paper_id}/feedback", response_model=Feedback)
def submit_paper_feedback(
    paper_id: str, body: PaperFeedbackRequest, db: Session = Depends(get_db)
):
    try:
        feedback = feedback_service.upsert_paper_feedback(db, paper_id, body.value)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Feedback(
        id=feedback.id,
        paper_id=feedback.paper_id,
        value=feedback.value,
        created_at=feedback.created_at,
    )


@router.get("/feedback/status", response_model=FeedbackStatus)
def get_feedback_status(db: Session = Depends(get_db)):
    pending_votes, pending_notes, pending_proposals = feedback_service.feedback_counts(
        db
    )
    return FeedbackStatus(
        pending_votes=pending_votes,
        pending_notes=pending_notes,
        pending_proposals=pending_proposals,
    )


@router.post("/feedback/process")
def trigger_feedback_processing(db: Session = Depends(get_db)):
    try:
        job_id = feedback_service.start_feedback_processing(db)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"job_id": job_id}
