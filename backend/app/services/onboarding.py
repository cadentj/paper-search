from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.config import settings
from app.models.filter import SQLAFilter
from app.models.job import SQLAJob
from app.models.onboarding_extraction import SQLAOnboardingExtraction
from app.models.research_profile_import import SQLAResearchProfileImport
from app.services.jobs import (
    commit_refresh,
    create_job,
    enqueue,
    latest_job_for_subject,
)

if TYPE_CHECKING:
    from app.api.onboarding import OnboardingCompleteRequest, OnboardingGenerationCreate


def start_generation(db: Session, body: OnboardingGenerationCreate) -> str:
    input_text = body.input_text.strip()
    if len(input_text) > settings.ONBOARDING_INPUT_MAX_CHARS:
        raise ValueError(
            f"Input text must be {settings.ONBOARDING_INPUT_MAX_CHARS} characters or fewer"
        )
    if not input_text and not body.document_ids:
        raise ValueError("Add text or at least one document")

    job_record = create_job(
        db,
        kind="onboarding_generation",
        subject_type="onboarding_generation",
        status="queued",
        payload={
            "input_text": input_text,
            "document_ids": list(body.document_ids),
        },
    )
    db.flush()
    job_record.subject_id = job_record.id
    commit_refresh(db, job_record)
    enqueue(db, job_record, log_context=f"onboarding generation={job_record.id}")
    return job_record.id


def start_extraction(db: Session, input_text: str) -> str:
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
    commit_refresh(db, extraction, job_record)
    enqueue(db, job_record, log_context=f"onboarding extraction={extraction.id}")
    return job_record.id


def draft_filters_for_generation(db: Session, job_id: str) -> list[SQLAFilter]:
    return [
        filter
        for filter in db.query(SQLAFilter)
        .filter(SQLAFilter.status == "draft")
        .order_by(SQLAFilter.created_at.asc(), SQLAFilter.id.asc())
        .all()
        if (filter.definition or {}).get("onboarding_generation_job_id") == job_id
    ]


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


def get_extraction(db: Session, extraction_id: str) -> SQLAOnboardingExtraction:
    extraction = (
        db.query(SQLAOnboardingExtraction)
        .filter(SQLAOnboardingExtraction.id == extraction_id)
        .first()
    )
    if not extraction:
        raise LookupError("Extraction not found")
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
    by_id = {filter.id: filter for filter in filters}
    ordered = [by_id[fid] for fid in filter_ids if fid in by_id]
    missing = [fid for fid in filter_ids if fid not in by_id]
    if missing:
        raise LookupError(f"Draft filter not found: {missing[0]}")

    for filter in ordered:
        if filter.status != "draft":
            raise ValueError(f"Filter is not a draft: {filter.id}")
        filter.status = "active"
        filter.updated_at = now

    db.flush()
    for filter in ordered:
        db.refresh(filter)
    return ordered


def complete_onboarding(
    db: Session, body: OnboardingCompleteRequest
) -> list[SQLAFilter]:
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
        filter = SQLAFilter(
            id=str(uuid.uuid4()),
            name=name,
            definition=definition,
            status="active",
            created_at=now,
            updated_at=now,
        )
        db.add(filter)
        created_filters.append(filter)

    db.flush()
    for filter in created_filters:
        db.refresh(filter)
    return created_filters


def start_profile_import(
    db: Session,
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
    commit_refresh(db, profile_import, job_record)
    enqueue(db, job_record)
    return profile_import.id, job_record.id


def get_import(db: Session, import_id: str) -> SQLAResearchProfileImport:
    profile_import = (
        db.query(SQLAResearchProfileImport)
        .filter(SQLAResearchProfileImport.id == import_id)
        .first()
    )
    if not profile_import:
        raise LookupError("Import not found")
    return profile_import
