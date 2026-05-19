from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.jobs.feedback_reflection import process_all_feedback
from app.jobs.queues import enqueue_for_job
from app.models.filter import SQLAFilter
from paper_search_core.models.paper import SQLAPaper
from app.models.paper_match import SQLAPaperMatch
from app.models.paper_match_feedback import SQLAPaperMatchFeedback
from app.models.paper_note import SQLAPaperNote
from app.services.job_enqueue import commit_entities, enqueue_job, mark_job_failed
from app.services.jobs import create_job


def upsert_match_feedback(
    db: Session, match_id: str, value: str
) -> SQLAPaperMatchFeedback:
    if value not in ("up", "down"):
        raise ValueError("value must be 'up' or 'down'")

    match = db.query(SQLAPaperMatch).filter(SQLAPaperMatch.id == match_id).first()
    if not match:
        raise LookupError("Match not found")

    now = datetime.now(timezone.utc)
    existing = (
        db.query(SQLAPaperMatchFeedback)
        .filter(SQLAPaperMatchFeedback.paper_match_id == match_id)
        .first()
    )
    if existing:
        existing.value = value
        existing.updated_at = now
        existing.processed = False
        feedback = existing
    else:
        feedback = SQLAPaperMatchFeedback(
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


def upsert_paper_feedback(
    db: Session, paper_id: str, value: str
) -> SQLAPaperMatchFeedback:
    if value != "up":
        raise ValueError("Only 'up' is allowed for unmatched papers")

    paper = db.query(SQLAPaper).filter(SQLAPaper.id == paper_id).first()
    if not paper:
        raise LookupError("Paper not found")

    now = datetime.now(timezone.utc)
    existing = (
        db.query(SQLAPaperMatchFeedback)
        .filter(
            SQLAPaperMatchFeedback.paper_id == paper_id,
            SQLAPaperMatchFeedback.paper_match_id.is_(None),
        )
        .first()
    )
    if existing:
        existing.updated_at = now
        existing.processed = False
        feedback = existing
    else:
        feedback = SQLAPaperMatchFeedback(
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
        db.query(SQLAPaperMatchFeedback)
        .filter(SQLAPaperMatchFeedback.processed == False)
        .count()
    )
    pending_notes = (
        db.query(SQLAPaperNote)
        .filter(SQLAPaperNote.processed == False, SQLAPaperNote.text != "")
        .count()
    )
    pending_proposals = (
        db.query(SQLAFilter)
        .filter(
            SQLAFilter.status.in_(
                ["pending_create", "pending_revision", "pending_deletion"]
            )
        )
        .count()
    )
    return pending_votes, pending_notes, pending_proposals


def start_feedback_processing(db: Session) -> str:
    pending_votes, pending_notes, _ = feedback_counts(db)
    if pending_votes == 0 and pending_notes == 0:
        raise ValueError("No pending feedback to process")

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
        enqueue=lambda: enqueue_for_job(
            job_record, process_all_feedback, job_record.id
        ),
        on_failure=lambda sess, error: mark_job_failed(sess, job_record, error),
    )
    return job_record.id
