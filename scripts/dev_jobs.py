#!/usr/bin/env python3
"""Development helpers for reconciling app job state after worker interrupts."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for path in (REPO_ROOT / "backend", REPO_ROOT / "core" / "src"):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from app.db.session import database  # noqa: E402
from app.models import (  # noqa: E402
    SQLADocument,
    SQLAIdeaMap,
    SQLAJob,
    SQLAOnboardingExtraction,
    SQLAResearchProfileImport,
    SQLASearchRun,
)
from app.services.jobs import set_job_status  # noqa: E402

ACTIVE_STATUSES = ("queued", "running")


def _fail_subject(db, job: SQLAJob, *, message: str, now: datetime) -> None:
    if not job.subject_type or not job.subject_id:
        return

    if job.subject_type == "search_run" and job.kind == "daily_search":
        run = db.query(SQLASearchRun).filter(SQLASearchRun.id == job.subject_id).first()
        if run and run.status in ACTIVE_STATUSES:
            run.status = "failed"
            run.error = message
            run.completed_at = now
        return

    if job.subject_type == "document":
        document = (
            db.query(SQLADocument).filter(SQLADocument.id == job.subject_id).first()
        )
        if document and document.status in ACTIVE_STATUSES:
            document.status = "failed"
            document.error = message
        return

    if job.subject_type == "onboarding_extraction":
        extraction = (
            db.query(SQLAOnboardingExtraction)
            .filter(SQLAOnboardingExtraction.id == job.subject_id)
            .first()
        )
        if extraction and extraction.status in ACTIVE_STATUSES:
            extraction.status = "failed"
            extraction.error = message
            extraction.completed_at = now
        return

    if job.subject_type == "idea_map":
        idea_map = (
            db.query(SQLAIdeaMap).filter(SQLAIdeaMap.id == job.subject_id).first()
        )
        if idea_map and idea_map.status in ACTIVE_STATUSES:
            idea_map.status = "failed"
            idea_map.error = message
        return

    if job.subject_type == "research_profile_import":
        profile_import = (
            db.query(SQLAResearchProfileImport)
            .filter(SQLAResearchProfileImport.id == job.subject_id)
            .first()
        )
        if profile_import and profile_import.status in ("pending", "running"):
            profile_import.status = "failed"
            profile_import.error = message


def fail_jobs(statuses: tuple[str, ...], *, message: str) -> int:
    now = datetime.now(timezone.utc)
    with database.session() as db:
        jobs = db.query(SQLAJob).filter(SQLAJob.status.in_(statuses)).all()
        for job in jobs:
            set_job_status(job, status="failed", error=message)
            _fail_subject(db, job, message=message, now=now)
        return len(jobs)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    fail_running = subparsers.add_parser("fail-running")
    fail_running.add_argument("message")

    fail_active = subparsers.add_parser("fail-active")
    fail_active.add_argument("message")

    args = parser.parse_args()
    if args.command == "fail-running":
        count = fail_jobs(("running",), message=args.message)
    else:
        count = fail_jobs(ACTIVE_STATUSES, message=args.message)
    print(f"Marked {count} job(s) failed.")


if __name__ == "__main__":
    main()
