import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.schemas.job import JobStart
from app.db.session import get_db
from app.models.job import Job
from app.models.paper_match import PaperMatch
from app.models.search_run import SearchRun
from app.utils.cursor import apply_cursor, decode_cursor, encode_cursor
from paper_search_core.daily_dates import DAILY_SEARCH_DATE_SET
from app.services.sources import counts_by_source_for_date, enabled_source_types
from app.services import jobs, search_runs

router = APIRouter(prefix="/search-runs", tags=["search"])
logger = logging.getLogger(__name__)


class SummaryCitation(BaseModel):
    paperMatchId: Optional[str] = None
    arxivId: Optional[str] = None
    itemId: Optional[str] = None
    sourceType: Optional[str] = None
    sourceId: Optional[str] = None
    citedFor: str = ""


class DailySearchSummary(BaseModel):
    search_run_id: str
    summary: str
    citations: list[SummaryCitation] = Field(default_factory=list)


class CreateDailySearchRequest(BaseModel):
    run_date: date | None = None


class DailyCandidateCount(BaseModel):
    date: date
    count: int
    counts_by_source: dict = Field(default_factory=dict)


class DailySearchJob(BaseModel):
    job: Job
    subject: SearchRun
    items: list[PaperMatch] = Field(default_factory=list)
    next_cursor: str | None = None
    done: bool = False


class DailySearchSummaryJob(BaseModel):
    job: Job
    run: SearchRun
    summary: DailySearchSummary | None = None
    done: bool = False


@router.get("/jobs/{job_id}", response_model=DailySearchJob)
def get_daily_search_job(
    job_id: str,
    cursor: str | None = None,
    db: Session = Depends(get_db),
):
    job = jobs.get_job_of_kind(db, job_id, "daily_search")
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    run = search_runs.get_search_run_for_job(db, job)
    if not run:
        raise HTTPException(status_code=404, detail="Search run not found")
    if cursor is not None:
        try:
            decode_cursor(cursor)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid cursor") from exc
    all_matches = search_runs.list_matches_for_run_ordered(db, run.id)
    matches = apply_cursor(all_matches, cursor)
    next_cursor = cursor
    if matches:
        latest = matches[-1]
        next_cursor = encode_cursor(latest.created_at, latest.id)
    return DailySearchJob(
        job=search_runs.serialize_daily_search_job(db, job, run),
        subject=run.to_pydantic(job_id=job.id),
        items=[search_runs.match_to_pydantic(db, match) for match in matches],
        next_cursor=next_cursor,
        done=jobs.is_done(job),
    )


@router.get("/summary-jobs/{job_id}", response_model=DailySearchSummaryJob)
def get_daily_search_summary_job(job_id: str, db: Session = Depends(get_db)):
    job = jobs.get_job_of_kind(db, job_id, "daily_search_summary")
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    run = search_runs.get_search_run_for_job(db, job)
    if not run:
        raise HTTPException(status_code=404, detail="Search run not found")
    return DailySearchSummaryJob(
        job=job.to_pydantic(),
        run=search_runs.search_run_payload(db, run),
        summary=search_runs.summary_payload(run),
        done=jobs.is_done(job),
    )


@router.get("", response_model=list[SearchRun])
def list_search_runs(db: Session = Depends(get_db)):
    return [
        search_runs.search_run_payload(db, run)
        for run in search_runs.list_search_runs(db)
    ]


@router.get("/latest", response_model=Optional[SearchRun])
def get_latest_search_run(db: Session = Depends(get_db)):
    run = search_runs.latest_search_run(db)
    return search_runs.search_run_payload(db, run) if run else None


@router.get("/daily-candidate-count", response_model=DailyCandidateCount)
def get_daily_candidate_count(run_date: date, db: Session = Depends(get_db)):
    if run_date not in DAILY_SEARCH_DATE_SET:
        raise HTTPException(
            status_code=400,
            detail=f"{run_date} is outside the configured daily search window",
        )
    counts_by_source = counts_by_source_for_date(db, enabled_source_types(db), run_date)
    return {
        "date": run_date,
        "count": sum(counts_by_source.values()),
        "counts_by_source": counts_by_source,
    }


@router.get("/{search_run_id}", response_model=SearchRun)
def get_search_run(search_run_id: str, db: Session = Depends(get_db)):
    try:
        run = search_runs.get_search_run(db, search_run_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return search_runs.search_run_payload(db, run)


@router.get("/{search_run_id}/summary", response_model=DailySearchSummary)
def get_search_run_summary(search_run_id: str, db: Session = Depends(get_db)):
    try:
        run = search_runs.get_search_run(db, search_run_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    summary = search_runs.summary_payload(run)
    if not summary:
        raise HTTPException(status_code=404, detail="Summary not available")
    return summary


@router.get("/{search_run_id}/matches", response_model=list[PaperMatch])
def get_search_run_matches(search_run_id: str, db: Session = Depends(get_db)):
    try:
        return search_runs.list_matches_for_run(db, search_run_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/daily", response_model=JobStart)
def create_daily_search_run(
    request: CreateDailySearchRequest | None = None,
    db: Session = Depends(get_db),
):
    try:
        run_date = request.run_date if request and request.run_date else None
        job = search_runs.start_daily_search(db, run_date=run_date)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JobStart(job_id=job.id)


@router.post("/{search_run_id}/summary", response_model=JobStart)
def create_daily_search_summary(search_run_id: str, db: Session = Depends(get_db)):
    try:
        job = search_runs.start_daily_summary(db, search_run_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JobStart(job_id=job.id)
