from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.jobs.feedback_reflection import process_all_feedback
from app.jobs.queue import get_queue
from app.models.filter import Filter
from app.models.paper import Paper
from app.models.paper_match import PaperMatch
from app.models.paper_match_feedback import PaperMatchFeedback
from app.models.paper_note import PaperNote
from app.services.errors import NotFound, ValidationFailed
from app.services.job_enqueue import commit_entities, enqueue_job, mark_job_failed
from app.services.jobs import create_job


def upsert_match_feedback(db: Session, match_id: str, value: str) -> PaperMatchFeedback:
    if value not in ("up", "down"):
        raise ValidationFailed("value must be 'up' or 'down'")

    match = db.query(PaperMatch).filter(PaperMatch.id == match_id).first()
    if not match:
        raise NotFound("Match not found")

    now = datetime.now(timezone.utc)
    existing = (
        db.query(PaperMatchFeedback)
        .filter(PaperMatchFeedback.paper_match_id == match_id)
        .first()
    )
    if existing:
        existing.value = value
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
            value=value,
            created_at=now,
            updated_at=now,
        )
        db.add(feedback)

    db.flush()
    db.refresh(feedback)
    return feedback


def upsert_paper_feedback(db: Session, paper_id: str, value: str) -> PaperMatchFeedback:
    if value != "up":
        raise ValidationFailed("Only 'up' is allowed for unmatched papers")

    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise NotFound("Paper not found")

    now = datetime.now(timezone.utc)
    existing = (
        db.query(PaperMatchFeedback)
        .filter(
            PaperMatchFeedback.paper_id == paper_id,
            PaperMatchFeedback.paper_match_id.is_(None),
        )
        .first()
    )
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
    return feedback


def feedback_counts(db: Session) -> tuple[int, int, int]:
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
    return pending_votes, pending_notes, pending_proposals


def start_feedback_processing(db: Session) -> str:
    pending_votes, pending_notes, _ = feedback_counts(db)
    if pending_votes == 0 and pending_notes == 0:
        raise ValidationFailed("No pending feedback to process")

    job_record = create_job(
        db,
        kind="feedback_reflection",
        subject_type="feedback_batch",
        subject_id="batch",
    )
    commit_entities(db, job_record)

    enqueue_job(
        db,
        job=job_record,
        enqueue=lambda: get_queue().enqueue(process_all_feedback, job_record.id),
        on_failure=lambda sess, error: mark_job_failed(sess, job_record, error),
        store_queue_job_id=False,
    )
    return job_record.id
