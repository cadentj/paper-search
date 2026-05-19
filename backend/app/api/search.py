import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.http_errors import raise_http_from_service
from app.db.session import get_db
from app.schemas.search import (
    CreateDailySearchRequest,
    DailyCandidateCountResponse,
    DailySearchSummaryResponse,
    SearchRunResponse,
    PaperMatchResponse,
)
from app.schemas.jobs import JobStartResponse
from paper_search_core.daily_dates import DAILY_SEARCH_DATE_SET
from app.services.source_providers import counts_by_source_for_date
from app.services.source_settings import enabled_source_types, ensure_default_data_sources
from app.services import search_runs

router = APIRouter(prefix="/search-runs", tags=["search"])
logger = logging.getLogger(__name__)


@router.get("", response_model=list[SearchRunResponse])
def list_search_runs(db: Session = Depends(get_db)):
    return [search_runs.search_run_payload(db, run) for run in search_runs.list_search_runs(db)]


@router.get("/latest", response_model=Optional[SearchRunResponse])
def get_latest_search_run(db: Session = Depends(get_db)):
    run = search_runs.latest_search_run(db)
    return search_runs.search_run_payload(db, run) if run else None


@router.get("/daily-candidate-count", response_model=DailyCandidateCountResponse)
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


@router.post("/daily", response_model=JobStartResponse)
def create_daily_search_run(
    request: CreateDailySearchRequest | None = None,
    db: Session = Depends(get_db),
):
    try:
        run_date = request.run_date if request and request.run_date else None
        job = search_runs.start_daily_search(db, run_date=run_date)
    except Exception as exc:
        raise_http_from_service(exc)
    return JobStartResponse(job_id=job.id)


@router.get("/{search_run_id}", response_model=SearchRunResponse)
def get_search_run(search_run_id: str, db: Session = Depends(get_db)):
    try:
        run = search_runs.get_search_run(db, search_run_id)
    except Exception as exc:
        raise_http_from_service(exc)
    return search_runs.search_run_payload(db, run)


@router.get("/{search_run_id}/summary", response_model=DailySearchSummaryResponse)
def get_search_run_summary(search_run_id: str, db: Session = Depends(get_db)):
    try:
        run = search_runs.get_search_run(db, search_run_id)
    except Exception as exc:
        raise_http_from_service(exc)
    summary = search_runs.summary_payload(run)
    if not summary:
        raise HTTPException(status_code=404, detail="Summary not available")
    return summary


@router.get("/{search_run_id}/matches", response_model=list[PaperMatchResponse])
def get_search_run_matches(search_run_id: str, db: Session = Depends(get_db)):
    try:
        return search_runs.list_matches_for_run(db, search_run_id)
    except Exception as exc:
        raise_http_from_service(exc)


@router.post("/{search_run_id}/summary", response_model=JobStartResponse)
def create_daily_search_summary(search_run_id: str, db: Session = Depends(get_db)):
    try:
        job = search_runs.start_daily_summary(db, search_run_id)
    except Exception as exc:
        raise_http_from_service(exc)
    return JobStartResponse(job_id=job.id)
