from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.jobs.queue import get_queue
from app.jobs.scholar_import import run_scholar_import
from app.models.research_profile_import import ResearchProfileImport
from app.services.errors import NotFound
from app.services.job_enqueue import persist_then_enqueue
from app.services.jobs import create_job, set_job_status


def start_profile_import(
    db: Session,
    *,
    url: str,
    author_id: str,
    display_name: str,
) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    profile_import = ResearchProfileImport(
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


def get_import(db: Session, import_id: str) -> ResearchProfileImport:
    profile_import = (
        db.query(ResearchProfileImport)
        .filter(ResearchProfileImport.id == import_id)
        .first()
    )
    if not profile_import:
        raise NotFound("Import not found")
    return profile_import
