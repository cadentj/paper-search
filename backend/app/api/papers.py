import uuid
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.paper import Paper
from app.models.idea_map import IdeaMap
from app.schemas.papers import PaperResponse, IdeaMapResponse
from app.schemas.jobs import JobStartResponse
from app.jobs.queue import get_queue
from app.jobs.idea_map import generate_idea_map
from app.services.jobs import build_progress, create_job, latest_job_for_subject
from app.services.html_parser import prepare_arxiv_html_for_viewer
from app.services.paper_html_source import arxiv_html_url, read_paper_html
from app.services.public_lesswrong_cache import fetch_public_post_html

router = APIRouter(prefix="/papers", tags=["papers"])
logger = logging.getLogger(__name__)


@router.get("/{paper_id}", response_model=PaperResponse)
def get_paper(paper_id: str, db: Session = Depends(get_db)):
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper


@router.get("/{paper_id}/html")
def get_paper_html(paper_id: str, db: Session = Depends(get_db)):
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    if paper.source_type == "lesswrong":
        try:
            post_html = fetch_public_post_html(
                html_url=paper.html_url,
                html_key=(paper.source_metadata or {}).get("html_key"),
            )
        except Exception:
            logger.exception("failed to fetch LessWrong HTML for paper=%s", paper.id)
            post_html = None
        if post_html:
            return {
                "html": post_html,
                "source_url": paper.source_url or paper.landing_url,
            }
        return {
            "html": None,
            "source_url": paper.source_url or paper.landing_url,
        }

    paper_html = read_paper_html(paper.arxiv_id, html_url=paper.html_url)
    if paper_html:
        return {
            "html": prepare_arxiv_html_for_viewer(
                paper_html.html,
                paper_html.source_url,
            ),
            "source_url": paper_html.source_url,
        }

    return {
        "html": None,
        "source_url": arxiv_html_url(paper.arxiv_id) if paper.arxiv_id else None,
    }


@router.post("/{paper_id}/idea-map", response_model=JobStartResponse)
def create_or_get_idea_map(paper_id: str, db: Session = Depends(get_db)):
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    existing = db.query(IdeaMap).filter(IdeaMap.paper_id == paper_id).first()
    if existing:
        if existing.status in {"queued", "running", "claims_running", "warrants_running"}:
            job = latest_job_for_subject(
                db,
                subject_type="idea_map",
                subject_id=existing.id,
                kind="idea_map",
            )
            if not job:
                job = create_job(
                    db,
                    kind="idea_map",
                    subject_type="idea_map",
                    subject_id=existing.id,
                    status=existing.status,
                    progress=build_progress(
                        stage=existing.status,
                        current=0,
                        total=1,
                        message=f"Idea map is {existing.status}",
                    ),
                )
                db.commit()
                db.refresh(job)
            return JobStartResponse(job_id=job.id)

        existing.status = "queued"
        existing.claims = []
        existing.dropped_reason = None
        existing.error = None
        existing.updated_at = datetime.now(timezone.utc)
        job_record = create_job(
            db,
            kind="idea_map",
            subject_type="idea_map",
            subject_id=existing.id,
            status="queued",
            progress=build_progress(
                stage="queued",
                current=0,
                total=1,
                message="Queued, waiting for worker",
            ),
        )
        db.commit()
        db.refresh(existing)
        db.refresh(job_record)
        return _enqueue_idea_map(existing, db, job_record)

    now = datetime.now(timezone.utc)
    idea_map = IdeaMap(
        id=str(uuid.uuid4()),
        paper_id=paper_id,
        status="queued",
        created_at=now,
        updated_at=now,
    )
    db.add(idea_map)
    job_record = create_job(
        db,
        kind="idea_map",
        subject_type="idea_map",
        subject_id=idea_map.id,
        status="queued",
        progress=build_progress(
            stage="queued",
            current=0,
            total=1,
            message="Queued, waiting for worker",
        ),
    )
    db.commit()
    db.refresh(idea_map)
    db.refresh(job_record)

    return _enqueue_idea_map(idea_map, db, job_record)


def _enqueue_idea_map(idea_map: IdeaMap, db: Session, job_record) -> JobStartResponse:
    try:
        q = get_queue()
        job = q.enqueue(generate_idea_map, idea_map.id, job_record.id)
        job_record.queue_job_id = getattr(job, "id", None)
        db.commit()
        logger.info("enqueued idea map=%s job=%s", idea_map.id, getattr(job, "id", None))
    except Exception as exc:
        logger.exception("failed to enqueue idea map=%s", idea_map.id)
        idea_map.status = "failed"
        idea_map.error = f"Could not enqueue idea map generation: {exc}"
        idea_map.updated_at = datetime.now(timezone.utc)
        job_record.status = "failed"
        job_record.error = idea_map.error
        job_record.completed_at = idea_map.updated_at
        job_record.progress = build_progress(
            stage="failed",
            current=0,
            total=1,
            message="Could not enqueue idea map generation. Is Redis running?",
            log=(job_record.progress or {}).get("log", []),
        )
        db.commit()
        raise HTTPException(status_code=503, detail=idea_map.error) from exc

    return JobStartResponse(job_id=job_record.id)


@router.get("/{paper_id}/idea-map", response_model=IdeaMapResponse)
def get_idea_map(paper_id: str, db: Session = Depends(get_db)):
    idea_map = db.query(IdeaMap).filter(IdeaMap.paper_id == paper_id).first()
    if not idea_map:
        raise HTTPException(status_code=404, detail="Idea map not found")
    return idea_map
