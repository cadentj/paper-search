import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.feedback import Feedback
from app.models.filter import Filter
from app.schemas.feedback import FeedbackCreate, FeedbackResponse

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("", response_model=FeedbackResponse)
def submit_feedback(body: FeedbackCreate, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    fb = Feedback(
        id=str(uuid.uuid4()),
        target_type=body.target_type,
        target_id=body.target_id,
        value=body.value,
        note=body.note,
        created_at=now,
    )
    db.add(fb)

    if body.target_type == "filter" and body.value == "not_interested":
        filt = db.query(Filter).filter(Filter.id == body.target_id).first()
        if filt:
            filt.status = "archived"
            filt.archived_at = now
            filt.updated_at = now

    db.commit()
    db.refresh(fb)
    return fb
