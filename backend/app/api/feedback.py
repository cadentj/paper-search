import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.filter import Filter
from app.models.paper_match import PaperMatch
from app.models.paper_match_feedback import PaperMatchFeedback
from app.services.jobs import create_job
from app.jobs.queue import get_queue
from app.jobs.feedback_reflection import reflect_on_feedback

router = APIRouter(tags=["feedback"])


class FeedbackRequest(BaseModel):
    value: str  # "up" or "down"


class FeedbackResponse(BaseModel):
    id: str
    paper_match_id: str
    value: str
    created_at: datetime


class NotificationCountResponse(BaseModel):
    unseen_count: int


@router.post("/paper-matches/{match_id}/feedback", response_model=FeedbackResponse)
def submit_feedback(match_id: str, body: FeedbackRequest, db: Session = Depends(get_db)):
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

    db.commit()
    db.refresh(feedback)

    job = create_job(
        db,
        kind="feedback_reflection",
        subject_type="paper_match_feedback",
        subject_id=feedback.id,
    )
    db.commit()

    try:
        q = get_queue()
        q.enqueue(reflect_on_feedback, feedback.id, job.id)
    except Exception:
        pass

    return FeedbackResponse(
        id=feedback.id,
        paper_match_id=feedback.paper_match_id,
        value=feedback.value,
        created_at=feedback.created_at,
    )


@router.get("/feedback/notifications", response_model=NotificationCountResponse)
def get_feedback_notifications(db: Session = Depends(get_db)):
    unseen = (
        db.query(Filter)
        .filter(
            Filter.source == "feedback",
            Filter.status == "draft",
        )
        .count()
    )
    return NotificationCountResponse(unseen_count=unseen)


@router.post("/feedback/notifications/seen")
def mark_feedback_seen(db: Session = Depends(get_db)):
    return {"ok": True}
