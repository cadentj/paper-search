from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.jobs.idea_map import generate_idea_map
from app.jobs.queues import enqueue_for_job
from app.models.idea_map import SQLAIdeaMap
from paper_search_core.models.paper import SQLAPaper
from app.models.paper_note import SQLAPaperNote
from app.models.job import SQLAJob
from app.services.job_enqueue import commit_entities, enqueue_job
from app.services.jobs import create_job, latest_job_for_subject, set_job_status

logger = logging.getLogger(__name__)

IN_FLIGHT_IDEA_MAP_STATUSES = {
    "queued",
    "running",
    "claims_running",
    "warrants_running",
}


def get_paper(db: Session, paper_id: str) -> SQLAPaper:
    paper = db.query(SQLAPaper).filter(SQLAPaper.id == paper_id).first()
    if not paper:
        raise LookupError("Paper not found")
    return paper


def list_papers_for_date(
    db: Session, run_date: date, *, page: int, per_page: int
) -> tuple[list[SQLAPaper], int]:
    query = db.query(SQLAPaper).filter(func.date(SQLAPaper.published_at) == run_date)
    total = query.count()
    papers = (
        query.order_by(SQLAPaper.title)
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return papers, total


def get_idea_map_for_paper(db: Session, paper_id: str) -> SQLAIdeaMap:
    idea_map = db.query(SQLAIdeaMap).filter(SQLAIdeaMap.paper_id == paper_id).first()
    if not idea_map:
        raise LookupError("Idea map not found")
    return idea_map


def idea_map_payload(db: Session, idea_map: SQLAIdeaMap):
    job = latest_job_for_subject(
        db,
        subject_type="idea_map",
        subject_id=idea_map.id,
        kind="idea_map",
    )
    return idea_map.to_pydantic(job_id=job.id if job else None)


def upsert_paper_note(db: Session, paper_id: str, text: str) -> SQLAPaperNote:
    get_paper(db, paper_id)
    now = datetime.now(timezone.utc)
    note = db.query(SQLAPaperNote).filter(SQLAPaperNote.paper_id == paper_id).first()
    if note:
        note.text = text
        note.updated_at = now
    else:
        note = SQLAPaperNote(
            id=str(uuid.uuid4()),
            paper_id=paper_id,
            text=text,
            created_at=now,
            updated_at=now,
        )
        db.add(note)
    db.flush()
    db.refresh(note)
    return note


def get_paper_note(db: Session, paper_id: str) -> SQLAPaperNote | None:
    get_paper(db, paper_id)
    return db.query(SQLAPaperNote).filter(SQLAPaperNote.paper_id == paper_id).first()


def start_idea_map(db: Session, paper_id: str) -> str:
    get_paper(db, paper_id)
    existing = db.query(SQLAIdeaMap).filter(SQLAIdeaMap.paper_id == paper_id).first()

    if existing:
        if existing.status in IN_FLIGHT_IDEA_MAP_STATUSES:
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
                commit_entities(db, job)
            return job.id

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
        commit_entities(db, existing, job_record)
        _enqueue_idea_map(db, existing, job_record)
        return job_record.id

    now = datetime.now(timezone.utc)
    idea_map = SQLAIdeaMap(
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
    commit_entities(db, idea_map, job_record)
    _enqueue_idea_map(db, idea_map, job_record)
    return job_record.id


def _enqueue_idea_map(db: Session, idea_map: SQLAIdeaMap, job_record: SQLAJob) -> None:
    def on_failure(sess: Session, error: str) -> None:
        idea_map.status = "failed"
        idea_map.error = f"Could not enqueue idea map generation: {error}"
        idea_map.updated_at = datetime.now(timezone.utc)
        set_job_status(job_record, status="failed", error=idea_map.error)

    enqueue_job(
        db,
        job=job_record,
        enqueue=lambda: enqueue_for_job(
            job_record, generate_idea_map, idea_map.id, job_record.id
        ),
        on_failure=on_failure,
        log_context=f"idea map={idea_map.id}",
    )


def resolve_idea_map_job(db: Session, idea_map_id: str, job_id: str | None) -> SQLAJob:
    if job_id:
        job = db.query(SQLAJob).filter(SQLAJob.id == job_id).first()
        if job:
            return job
    from app.services.jobs import get_or_create_job_for_subject

    return get_or_create_job_for_subject(
        db,
        kind="idea_map",
        subject_type="idea_map",
        subject_id=idea_map_id,
    )


def get_idea_map(db: Session, idea_map_id: str) -> SQLAIdeaMap | None:
    return db.query(SQLAIdeaMap).filter(SQLAIdeaMap.id == idea_map_id).first()


def mark_idea_map_running(db: Session, idea_map: SQLAIdeaMap, job: SQLAJob) -> None:
    idea_map.status = "running"
    idea_map.updated_at = datetime.now(timezone.utc)
    set_job_status(job, status="running")
    db.commit()


def mark_idea_map_skipped(
    db: Session, idea_map: SQLAIdeaMap, job: SQLAJob, reason: str
) -> None:
    idea_map.status = "skipped"
    idea_map.dropped_reason = reason
    idea_map.updated_at = datetime.now(timezone.utc)
    set_job_status(job, status="skipped")
    db.commit()


def commit_idea_map(db: Session) -> None:
    db.commit()


def fail_idea_map(db: Session, idea_map: SQLAIdeaMap, job: SQLAJob, error: str) -> None:
    idea_map.status = "failed"
    idea_map.error = error
    idea_map.updated_at = datetime.now(timezone.utc)
    set_job_status(job, status="failed", error=error)
    db.commit()
