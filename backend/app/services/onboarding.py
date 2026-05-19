from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.core.config import settings
from app.jobs.onboarding import extract_onboarding_filters, generate_onboarding_draft_filters
from app.jobs.queue import get_queue
from app.jobs.scholar_import import run_scholar_import
from app.models.filter import SQLAFilter
from app.models.onboarding_extraction import SQLAOnboardingExtraction
from app.models.research_profile_import import SQLAResearchProfileImport
from app.services.errors import EnqueueFailed, NotFound, ValidationFailed
from app.services.job_enqueue import commit_entities, enqueue_job, persist_then_enqueue
from app.services.jobs import create_job, latest_job_for_subject, set_job_status

if TYPE_CHECKING:
    from app.api.onboarding import OnboardingCompleteRequest, OnboardingGenerationCreate


def onboarding_status(db: Session) -> tuple[bool, int]:
    active_count = (
        db.query(SQLAFilter).filter(SQLAFilter.status == "active").count()
    )
    return active_count > 0, active_count


def start_generation(db: Session, body: OnboardingGenerationCreate) -> str:
    input_text = body.input_text.strip()
    if len(input_text) > settings.ONBOARDING_INPUT_MAX_CHARS:
        raise ValidationFailed(
            f"Input text must be {settings.ONBOARDING_INPUT_MAX_CHARS} characters or fewer"
        )
    if not input_text and not body.document_ids:
        raise ValidationFailed("Add text or at least one document")

    job_record = create_job(
        db,
        kind="onboarding_generation",
        subject_type="onboarding_generation",
        status="queued",
    )
    db.flush()
    job_record.subject_id = job_record.id
    commit_entities(db, job_record)

    def on_failure(sess: Session, error: str) -> None:
        set_job_status(
            job_record,
            status="failed",
            error=f"Could not enqueue onboarding generation: {error}",
        )

    enqueue_job(
        db,
        job=job_record,
        enqueue=lambda: get_queue().enqueue(
            generate_onboarding_draft_filters,
            input_text,
            body.document_ids,
            job_record.id,
        ),
        on_failure=on_failure,
        log_context=f"onboarding generation={job_record.id}",
    )
    return job_record.id


def start_extraction(db: Session, *, input_text: str) -> str:
    now = datetime.now(timezone.utc)
    extraction = SQLAOnboardingExtraction(
        id=str(uuid.uuid4()),
        input_text=input_text,
        status="queued",
        created_at=now,
        updated_at=now,
    )
    db.add(extraction)
    job_record = create_job(
        db,
        kind="onboarding_extraction",
        subject_type="onboarding_extraction",
        subject_id=extraction.id,
        status="queued",
    )

    def on_failure(sess: Session, error: str) -> None:
        extraction.status = "failed"
        extraction.error = f"Could not enqueue onboarding extraction: {error}"
        extraction.updated_at = datetime.now(timezone.utc)
        set_job_status(job_record, status="failed", error=extraction.error)

    try:
        persist_then_enqueue(
            db,
            job=job_record,
            entities=(extraction,),
            enqueue=lambda: get_queue().enqueue(
                extract_onboarding_filters, extraction.id, job_record.id
            ),
            on_failure=on_failure,
            log_context=f"onboarding extraction={extraction.id}",
        )
    except EnqueueFailed as exc:
        raise EnqueueFailed(extraction.error or str(exc)) from exc
    return job_record.id


def get_extraction(db: Session, extraction_id: str) -> SQLAOnboardingExtraction:
    extraction = (
        db.query(SQLAOnboardingExtraction)
        .filter(SQLAOnboardingExtraction.id == extraction_id)
        .first()
    )
    if not extraction:
        raise NotFound("Extraction not found")
    return extraction


def extraction_payload(db: Session, extraction: SQLAOnboardingExtraction):
    job = latest_job_for_subject(
        db,
        subject_type="onboarding_extraction",
        subject_id=extraction.id,
        kind="onboarding_extraction",
    )
    return extraction.to_pydantic(job_id=job.id if job else None)


def promote_draft_filters(db: Session, filter_ids: list[str]) -> list[SQLAFilter]:
    if not filter_ids:
        return []

    now = datetime.now(timezone.utc)
    filters = db.query(SQLAFilter).filter(SQLAFilter.id.in_(filter_ids)).all()
    by_id = {filt.id: filt for filt in filters}
    ordered = [by_id[fid] for fid in filter_ids if fid in by_id]
    missing = [fid for fid in filter_ids if fid not in by_id]
    if missing:
        raise NotFound(f"Draft filter not found: {missing[0]}")

    for filt in ordered:
        if filt.status != "draft":
            raise ValidationFailed(f"Filter is not a draft: {filt.id}")
        filt.status = "active"
        filt.updated_at = now

    db.flush()
    for filt in ordered:
        db.refresh(filt)
    return ordered


def complete_onboarding(db: Session, body: OnboardingCompleteRequest) -> list[SQLAFilter]:
    created_filters = []
    now = datetime.now(timezone.utc)

    for f_data in body.filters:
        definition = f_data.get("definition", f_data)
        name = definition.get("name", f_data.get("name", "Unnamed Filter"))
        definition = {
            "name": name,
            "description": definition.get("description", ""),
            "mode": definition.get("mode", "topic"),
        }
        filt = SQLAFilter(
            id=str(uuid.uuid4()),
            name=name,
            definition=definition,
            status="active",
            created_at=now,
            updated_at=now,
        )
        db.add(filt)
        created_filters.append(filt)

    db.flush()
    for filt in created_filters:
        db.refresh(filt)
    return created_filters


def start_profile_import(
    db: Session,
    *,
    url: str,
    author_id: str,
    display_name: str,
) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    profile_import = SQLAResearchProfileImport(
        id=str(uuid.uuid4()),
        status="pending",
        source_type="semantic_scholar",
        source_url=url,
        external_author_id=author_id,
        display_name=display_name,
        created_at=now,
        updated_at=now,
    )
    db.add(profile_import)
    job_record = create_job(
        db,
        kind="scholar_import",
        subject_type="research_profile_import",
        subject_id=profile_import.id,
    )

    def on_failure(sess: Session, error: str) -> None:
        profile_import.status = "failed"
        profile_import.error = error
        set_job_status(job_record, status="failed", error=error)

    persist_then_enqueue(
        db,
        job=job_record,
        entities=(profile_import,),
        enqueue=lambda: get_queue().enqueue(
            run_scholar_import, profile_import.id, job_record.id
        ),
        on_failure=on_failure,
        store_queue_job_id=False,
    )
    return profile_import.id, job_record.id


def get_import(db: Session, import_id: str) -> SQLAResearchProfileImport:
    profile_import = (
        db.query(SQLAResearchProfileImport)
        .filter(SQLAResearchProfileImport.id == import_id)
        .first()
    )
    if not profile_import:
        raise NotFound("Import not found")
    return profile_import
