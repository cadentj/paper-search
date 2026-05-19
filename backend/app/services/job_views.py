from __future__ import annotations

import base64
import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.document import SQLADocument
from app.models.filter import SQLAFilter
from app.models.idea_map import SQLAIdeaMap
from app.models.job import SQLAJob
from app.models.onboarding_extraction import SQLAOnboardingExtraction
from app.models.paper_match import PaperMatch, SQLAPaperMatch
from app.models.search_run import SQLASearchRun
from app.models.job import Job

DONE_STATUSES = {"completed", "failed", "skipped"}


def get_job(db: Session, job_id: str) -> SQLAJob | None:
    return db.query(SQLAJob).filter(SQLAJob.id == job_id).first()


def get_job_of_kind(db: Session, job_id: str, kind: str) -> SQLAJob | None:
    job = get_job(db, job_id)
    if not job or job.kind != kind:
        return None
    return job


def is_done(job: SQLAJob) -> bool:
    return job.status in DONE_STATUSES


def with_progress(job: SQLAJob, **fields) -> Job:
    response = job.to_pydantic()
    progress = dict(response.progress or {})
    progress.update(fields)
    response.progress = progress
    return response


def paper_match_response(db: Session, match: SQLAPaperMatch) -> PaperMatch:
    from app.models.filter import SQLAFilter
    from paper_search_core.models.paper import SQLAPaper

    paper = db.query(SQLAPaper).filter(SQLAPaper.id == match.paper_id).first()
    filter = db.query(SQLAFilter).filter(SQLAFilter.id == match.filter_id).first()
    return match.to_pydantic(paper=paper, filter=filter)


def encode_cursor(value: datetime, item_id: str) -> str:
    payload = {"at": value.isoformat(), "id": item_id}
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(cursor: str | None) -> tuple[datetime, str] | None:
    if not cursor:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
        value = datetime.fromisoformat(payload["at"])
        if value.tzinfo is not None:
            value = value.replace(tzinfo=None)
        return value, str(payload["id"])
    except Exception as exc:
        raise ValueError("Invalid cursor") from exc


def apply_cursor(items: list, cursor: str | None) -> list:
    decoded = decode_cursor(cursor)
    if not decoded:
        return items
    value, item_id = decoded
    return [
        item
        for item in items
        if item.created_at > value or (item.created_at == value and item.id > item_id)
    ]


def draft_filters_for_generation(db: Session, job_id: str) -> list[SQLAFilter]:
    return [
        filter
        for filter in db.query(SQLAFilter)
        .filter(SQLAFilter.status == "draft")
        .order_by(SQLAFilter.created_at.asc(), SQLAFilter.id.asc())
        .all()
        if (filter.definition or {}).get("onboarding_generation_job_id") == job_id
    ]


def serialize_daily_search_job(db: Session, job: SQLAJob, run: SQLASearchRun) -> Job:
    stored = dict(job.progress or {})
    match_count = (
        db.query(SQLAPaperMatch).filter(SQLAPaperMatch.search_run_id == run.id).count()
    )
    current = stored.get("current", match_count)
    return with_progress(
        job,
        current=current,
        total=stored.get("total", max(match_count, 1)),
        matches=match_count,
    )


def serialize_onboarding_generation_job(db: Session, job: SQLAJob) -> Job:
    count = len(draft_filters_for_generation(db, job.id))
    return with_progress(job, current=count, total=max(count, 1))


def serialize_onboarding_extraction_job(
    db: Session, job: SQLAJob, extraction: SQLAOnboardingExtraction
) -> Job:
    count = len(extraction.proposed_filters or [])
    return with_progress(job, current=count, total=max(count, 1))


def serialize_idea_map_job(db: Session, job: SQLAJob, idea_map: SQLAIdeaMap) -> Job:
    claims = list(idea_map.claims or [])
    claim_count = len(claims)
    stored_total = (job.progress or {}).get("total")
    if idea_map.status == "warrants_running" and stored_total:
        return with_progress(job, current=claim_count, total=int(stored_total))
    return with_progress(job, current=claim_count, total=max(claim_count, 1))


def serialize_document_job(job: SQLAJob, document: SQLADocument) -> Job:
    if document.status in {"ready", "needs_ocr", "failed"}:
        current, total = 2, 2
    elif document.status == "processing":
        current, total = 1, 2
    else:
        current, total = 0, 2
    return with_progress(job, current=current, total=total)


def get_search_run_for_job(db: Session, job: SQLAJob) -> SQLASearchRun | None:
    if not job.subject_id:
        return None
    return db.query(SQLASearchRun).filter(SQLASearchRun.id == job.subject_id).first()


def get_idea_map_for_job(db: Session, job: SQLAJob) -> SQLAIdeaMap | None:
    if not job.subject_id:
        return None
    return db.query(SQLAIdeaMap).filter(SQLAIdeaMap.id == job.subject_id).first()


def get_extraction_for_job(
    db: Session, job: SQLAJob
) -> SQLAOnboardingExtraction | None:
    if not job.subject_id:
        return None
    return (
        db.query(SQLAOnboardingExtraction)
        .filter(SQLAOnboardingExtraction.id == job.subject_id)
        .first()
    )


def get_document_for_job(db: Session, job: SQLAJob) -> SQLADocument | None:
    if not job.subject_id:
        return None
    return db.query(SQLADocument).filter(SQLADocument.id == job.subject_id).first()


def list_matches_for_run_ordered(
    db: Session, search_run_id: str
) -> list[SQLAPaperMatch]:
    return (
        db.query(SQLAPaperMatch)
        .filter(SQLAPaperMatch.search_run_id == search_run_id)
        .order_by(SQLAPaperMatch.created_at.asc(), SQLAPaperMatch.id.asc())
        .all()
    )
