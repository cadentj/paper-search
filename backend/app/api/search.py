import uuid
import logging
from datetime import datetime, date, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.filter import Filter
from app.models.paper import Paper
from app.models.paper_match import PaperMatch
from app.models.search_run import SearchRun
from app.schemas.search import SearchRunResponse, PaperMatchResponse
from app.jobs.queue import get_queue
from app.jobs.daily_search import run_daily_search

router = APIRouter(prefix="/search-runs", tags=["search"])
logger = logging.getLogger(__name__)


@router.get("", response_model=list[SearchRunResponse])
def list_search_runs(db: Session = Depends(get_db)):
    runs = db.query(SearchRun).order_by(SearchRun.created_at.desc()).all()
    return runs


@router.get("/latest", response_model=Optional[SearchRunResponse])
def get_latest_search_run(db: Session = Depends(get_db)):
    run = db.query(SearchRun).order_by(SearchRun.created_at.desc()).first()
    return run


@router.post("/daily", response_model=SearchRunResponse)
def create_daily_search_run(db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    run = SearchRun(
        id=str(uuid.uuid4()),
        status="queued",
        stage="queued",
        run_date=date.today(),
        progress_current=0,
        progress_total=1,
        progress_message="Queued, waiting for worker",
        progress_log=[
            {
                "at": now.isoformat(),
                "stage": "queued",
                "message": "Queued, waiting for worker",
            }
        ],
        created_at=now,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        q = get_queue()
        job = q.enqueue(run_daily_search, run.id)
        logger.info("enqueued daily search run=%s job=%s", run.id, getattr(job, "id", None))
    except Exception as exc:
        logger.exception("failed to enqueue daily search run=%s", run.id)
        run.status = "failed"
        run.stage = "failed"
        run.error = f"Could not enqueue daily search: {exc}"
        run.progress_message = "Could not enqueue daily search. Is Redis running?"
        run.progress_log = list(run.progress_log or []) + [
            {
                "at": datetime.now(timezone.utc).isoformat(),
                "stage": "failed",
                "message": run.progress_message,
            }
        ]
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(status_code=503, detail=run.error) from exc

    return run


@router.get("/{search_run_id}", response_model=SearchRunResponse)
def get_search_run(search_run_id: str, db: Session = Depends(get_db)):
    run = db.query(SearchRun).filter(SearchRun.id == search_run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Search run not found")
    return run


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

    matches = [m for m in matches if m.stance != "irrelevant"]

    result = []
    for m in matches:
        paper = db.query(Paper).filter(Paper.id == m.paper_id).first()
        filt = db.query(Filter).filter(Filter.id == m.filter_id).first()

        match_resp = PaperMatchResponse(
            id=m.id,
            search_run_id=m.search_run_id,
            filter_id=m.filter_id,
            paper_id=m.paper_id,
            stance=m.stance,
            relevance_score=m.relevance_score,
            confidence=m.confidence,
            rationale=m.rationale,
            matched_claims=m.matched_claims,
            abstract_evidence=m.abstract_evidence,
            llm_model=m.llm_model,
            created_at=m.created_at,
            paper_title=paper.title if paper else None,
            paper_authors=paper.authors if paper else None,
            paper_arxiv_id=paper.arxiv_id if paper else None,
            paper_abstract=paper.abstract if paper else None,
            filter_name=filt.name if filt else None,
        )
        result.append(match_resp)

    result.sort(key=lambda x: x.relevance_score, reverse=True)
    return result
