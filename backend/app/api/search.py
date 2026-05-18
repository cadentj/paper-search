import logging
import uuid
from datetime import datetime, date, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.filter import Filter
from app.models.paper import Paper
from app.models.paper_match import PaperMatch
from app.models.search_run import SearchRun
from app.schemas.search import (
    CreateDailySearchRequest,
    DailyCandidateCountResponse,
    SearchRunResponse,
    PaperMatchResponse,
)
from app.schemas.jobs import JobStartResponse
from app.jobs.queue import get_queue
from app.jobs.daily_search import run_daily_search
from app.services.jobs import build_progress, create_job, latest_job_for_subject
from app.services.daily_dates import DAILY_SEARCH_DATE_SET, DEFAULT_DAILY_SEARCH_DATE
from app.services.source_providers import counts_by_source_for_date
from app.services.source_settings import enabled_source_types, ensure_default_data_sources

router = APIRouter(prefix="/search-runs", tags=["search"])
logger = logging.getLogger(__name__)


@router.get("", response_model=list[SearchRunResponse])
def list_search_runs(db: Session = Depends(get_db)):
    runs = db.query(SearchRun).order_by(SearchRun.created_at.desc()).all()
    return [_search_run_payload(run, db) for run in runs]


@router.get("/latest", response_model=Optional[SearchRunResponse])
def get_latest_search_run(db: Session = Depends(get_db)):
    run = db.query(SearchRun).order_by(SearchRun.created_at.desc()).first()
    return _search_run_payload(run, db) if run else None


@router.get("/daily-candidate-count", response_model=DailyCandidateCountResponse)
def get_daily_candidate_count(run_date: date, db: Session = Depends(get_db)):
    if run_date not in DAILY_SEARCH_DATE_SET:
        raise HTTPException(
            status_code=400,
            detail=f"{run_date} is outside the configured daily search window",
        )
    counts_by_source = counts_by_source_for_date(enabled_source_types(db), run_date)
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
    ensure_default_data_sources(db)
    requested_date = request.run_date if request and request.run_date else DEFAULT_DAILY_SEARCH_DATE
    if not requested_date:
        raise HTTPException(status_code=400, detail="No daily search dates are configured")
    if requested_date not in DAILY_SEARCH_DATE_SET:
        raise HTTPException(status_code=400, detail=f"{requested_date} is outside the configured daily search window")
    if not enabled_source_types(db):
        raise HTTPException(status_code=400, detail="No data sources are enabled")

    now = datetime.now(timezone.utc)
    run = SearchRun(
        id=str(uuid.uuid4()),
        status="queued",
        run_date=requested_date,
        created_at=now,
    )
    db.add(run)
    job_record = create_job(
        db,
        kind="daily_search",
        subject_type="search_run",
        subject_id=run.id,
        status="queued",
        progress=build_progress(
            stage="queued",
            current=0,
            total=1,
            message="Queued, waiting for worker",
        ),
    )
    db.commit()
    db.refresh(run)
    db.refresh(job_record)

    try:
        q = get_queue()
        job = q.enqueue(run_daily_search, run.id, job_record.id)
        job_record.queue_job_id = getattr(job, "id", None)
        db.commit()
        logger.info("enqueued daily search run=%s job=%s", run.id, getattr(job, "id", None))
    except Exception as exc:
        logger.exception("failed to enqueue daily search run=%s", run.id)
        run.status = "failed"
        run.error = f"Could not enqueue daily search: {exc}"
        run.completed_at = datetime.now(timezone.utc)
        job_record.status = "failed"
        job_record.error = run.error
        job_record.completed_at = run.completed_at
        job_record.progress = build_progress(
            stage="failed",
            current=0,
            total=1,
            message="Could not enqueue daily search. Is Redis running?",
            log=(job_record.progress or {}).get("log", []),
        )
        db.commit()
        raise HTTPException(status_code=503, detail=run.error) from exc

    return JobStartResponse(job_id=job_record.id)


def _parse_index_date(value: str | date | None) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(value)


@router.get("/{search_run_id}", response_model=SearchRunResponse)
def get_search_run(search_run_id: str, db: Session = Depends(get_db)):
    run = db.query(SearchRun).filter(SearchRun.id == search_run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Search run not found")
    return _search_run_payload(run, db)


@router.get("/{search_run_id}/matches", response_model=list[PaperMatchResponse])
def get_search_run_matches(
    search_run_id: str,
    db: Session = Depends(get_db),
):
    run = db.query(SearchRun).filter(SearchRun.id == search_run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Search run not found")

    matches = db.query(PaperMatch).filter(
        PaperMatch.search_run_id == search_run_id
    ).all()

    result = []
    for m in matches:
        paper = db.query(Paper).filter(Paper.id == m.paper_id).first()
        filt = db.query(Filter).filter(Filter.id == m.filter_id).first()

        match_resp = PaperMatchResponse(
            id=m.id,
            search_run_id=m.search_run_id,
            filter_id=m.filter_id,
            paper_id=m.paper_id,
            result=m.result,
            llm_model=m.llm_model,
            created_at=m.created_at,
            paper_title=paper.title if paper else None,
            paper_authors=paper.authors if paper else None,
            paper_arxiv_id=paper.arxiv_id if paper else None,
            paper_source_type=paper.source_type if paper else None,
            paper_source_id=paper.source_id if paper else None,
            paper_source_url=(paper.source_url or paper.landing_url) if paper else None,
            paper_item_label=_paper_item_label(paper) if paper else None,
            paper_abstract=paper.abstract if paper else None,
            filter_name=filt.name if filt else None,
        )
        result.append(match_resp)

    result.sort(key=lambda x: x.created_at, reverse=True)
    return result


def _paper_item_label(paper: Paper) -> str:
    source_type = paper.source_type or "arxiv"
    source_id = paper.source_id or paper.arxiv_id or paper.id
    return f"{source_type}:{source_id}"


def _search_run_payload(run: SearchRun, db: Session) -> dict:
    payload = SearchRunResponse.model_validate(run).model_dump()
    job = latest_job_for_subject(
        db,
        subject_type="search_run",
        subject_id=run.id,
        kind="daily_search",
    )
    payload["job_id"] = job.id if job else None
    return payload
