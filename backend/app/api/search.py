import uuid
import threading
from datetime import datetime, date, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.filter import Filter
from app.models.paper import Paper
from app.models.paper_match import PaperMatch
from app.models.search_run import SearchRun
from app.models.feedback import Feedback
from app.schemas.search import SearchRunResponse, PaperMatchResponse
from app.services.mock_papers import get_daily_papers
from app.jobs.queue import get_queue
from app.jobs.daily_search import run_daily_search

router = APIRouter(prefix="/search-runs", tags=["search"])


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
        run_date=date.today(),
        created_at=now,
    )
    db.add(run)

    daily_papers = get_daily_papers()
    for p_data in daily_papers:
        existing = db.query(Paper).filter(Paper.arxiv_id == p_data["arxiv_id"]).first()
        if existing:
            existing.title = p_data["title"]
            existing.abstract = p_data["abstract"]
            existing.authors = p_data["authors"]
            existing.categories = p_data.get("categories")
            existing.published_at = p_data.get("published_at")
            existing.html_url = p_data.get("html_url")
            existing.landing_url = p_data.get("landing_url")
            existing.updated_at = now
        else:
            paper = Paper(
                id=str(uuid.uuid4()),
                arxiv_id=p_data["arxiv_id"],
                title=p_data["title"],
                abstract=p_data["abstract"],
                authors=p_data["authors"],
                categories=p_data.get("categories"),
                published_at=p_data.get("published_at"),
                html_url=p_data.get("html_url"),
                landing_url=p_data.get("landing_url"),
                created_at=now,
                updated_at=now,
            )
            db.add(paper)

    db.commit()
    db.refresh(run)

    try:
        q = get_queue()
        q.enqueue(run_daily_search, run.id)
    except Exception:
        threading.Thread(
            target=run_daily_search,
            args=(run.id,),
            daemon=True,
        ).start()

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
    include_hidden: bool = Query(False),
    db: Session = Depends(get_db),
):
    run = db.query(SearchRun).filter(SearchRun.id == search_run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Search run not found")

    matches = db.query(PaperMatch).filter(
        PaperMatch.search_run_id == search_run_id
    ).all()

    if not include_hidden:
        hidden_ids = set()
        feedbacks = db.query(Feedback).filter(
            Feedback.target_type == "paper_match",
            Feedback.value == "not_interested",
        ).all()
        hidden_ids = {f.target_id for f in feedbacks}
        matches = [m for m in matches if m.id not in hidden_ids]

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
