from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.job import Job
from app.services import jobs
from app.services.jobs_overview import jobs_overview

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobOverviewResponse(BaseModel):
    job: Job
    href: str | None = None


class JobsOverviewResponse(BaseModel):
    active: list[JobOverviewResponse] = Field(default_factory=list)
    recent: list[JobOverviewResponse] = Field(default_factory=list)


@router.get("/overview", response_model=JobsOverviewResponse)
def get_jobs_overview(db: Session = Depends(get_db)):
    overview = jobs_overview(db)
    return JobsOverviewResponse(
        active=[
            JobOverviewResponse(
                job=entry.job,
                href=entry.href,
            )
            for entry in overview.active
        ],
        recent=[
            JobOverviewResponse(
                job=entry.job,
                href=entry.href,
            )
            for entry in overview.recent
        ],
    )


@router.get("/{job_id}", response_model=Job)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = jobs.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_pydantic()
