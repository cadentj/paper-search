from __future__ import annotations

import base64
import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.filter import Filter
from app.models.idea_map import IdeaMap
from app.models.job import Job
from app.models.onboarding_extraction import OnboardingExtraction
from app.models.paper_match import PaperMatch
from app.models.search_run import SearchRun
from app.schemas.jobs import JobResponse
from app.schemas.search import PaperMatchResponse
from app.services.errors import NotFound, ValidationFailed
from app.services.jobs import latest_job_for_subject
from app.services.search_runs import search_run_payload, summary_payload

DONE_STATUSES = {"completed", "failed", "skipped"}


def get_job(db: Session, job_id: str) -> Job:
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise NotFound("Job not found")
    return job


def get_job_of_kind(db: Session, job_id: str, kind: str) -> Job:
    job = get_job(db, job_id)
    if job.kind != kind:
        raise ValidationFailed(f"Job is not a {kind} job")
    return job


def is_done(job: Job) -> bool:
    return job.status in DONE_STATUSES


def with_progress(job: Job, **fields) -> JobResponse:
    response = job.to_pydantic()
    progress = dict(response.progress or {})
    progress.update(fields)
    response.progress = progress
    return response


def paper_match_response(db: Session, match: PaperMatch) -> PaperMatchResponse:
    from app.models.filter import Filter
    from app.models.paper import Paper

    paper = db.query(Paper).filter(Paper.id == match.paper_id).first()
    filt = db.query(Filter).filter(Filter.id == match.filter_id).first()
    return match.to_pydantic(paper=paper, filt=filt)


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
        raise ValidationFailed("Invalid cursor") from exc


def apply_cursor(items: list, cursor: str | None) -> list:
    decoded = decode_cursor(cursor)
    if not decoded:
        return items
    value, item_id = decoded
    return [
        item
        for item in items
        if item.created_at > value
        or (item.created_at == value and item.id > item_id)
    ]


def draft_filters_for_generation(db: Session, job_id: str) -> list[Filter]:
    return [
        filt
        for filt in db.query(Filter)
        .filter(Filter.status == "draft")
        .order_by(Filter.created_at.asc(), Filter.id.asc())
        .all()
        if (filt.definition or {}).get("onboarding_generation_job_id") == job_id
    ]


def serialize_daily_search_job(db: Session, job: Job, run: SearchRun) -> JobResponse:
    stored = dict(job.progress or {})
    match_count = (
        db.query(PaperMatch).filter(PaperMatch.search_run_id == run.id).count()
    )
    return with_progress(
        job,
        current=match_count,
        total=stored.get("total", max(match_count, 1)),
    )


def serialize_onboarding_generation_job(db: Session, job: Job) -> JobResponse:
    count = len(draft_filters_for_generation(db, job.id))
    return with_progress(job, current=count, total=max(count, 1))


def serialize_onboarding_extraction_job(
    db: Session, job: Job, extraction: OnboardingExtraction
) -> JobResponse:
    count = len(extraction.proposed_filters or [])
    return with_progress(job, current=count, total=max(count, 1))


def serialize_idea_map_job(db: Session, job: Job, idea_map: IdeaMap) -> JobResponse:
    claims = list(idea_map.claims or [])
    claim_count = len(claims)
    stored_total = (job.progress or {}).get("total")
    if idea_map.status == "warrants_running" and stored_total:
        return with_progress(job, current=claim_count, total=int(stored_total))
    return with_progress(job, current=claim_count, total=max(claim_count, 1))


def serialize_document_job(job: Job, document: Document) -> JobResponse:
    if document.status in {"ready", "needs_ocr", "failed"}:
        current, total = 2, 2
    elif document.status == "processing":
        current, total = 1, 2
    else:
        current, total = 0, 2
    return with_progress(job, current=current, total=total)


def get_search_run_for_job(db: Session, job: Job) -> SearchRun:
    run = db.query(SearchRun).filter(SearchRun.id == job.subject_id).first()
    if not run:
        raise NotFound("Search run not found")
    return run


def get_idea_map_for_job(db: Session, job: Job) -> IdeaMap:
    idea_map = db.query(IdeaMap).filter(IdeaMap.id == job.subject_id).first()
    if not idea_map:
        raise NotFound("Idea map not found")
    return idea_map


def get_extraction_for_job(db: Session, job: Job) -> OnboardingExtraction:
    extraction = (
        db.query(OnboardingExtraction)
        .filter(OnboardingExtraction.id == job.subject_id)
        .first()
    )
    if not extraction:
        raise NotFound("Extraction not found")
    return extraction


def get_document_for_job(db: Session, job: Job) -> Document:
    document = db.query(Document).filter(Document.id == job.subject_id).first()
    if not document:
        raise NotFound("Document not found")
    return document


def list_matches_for_run_ordered(db: Session, search_run_id: str) -> list[PaperMatch]:
    return (
        db.query(PaperMatch)
        .filter(PaperMatch.search_run_id == search_run_id)
        .order_by(PaperMatch.created_at.asc(), PaperMatch.id.asc())
        .all()
    )
