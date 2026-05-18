import uuid
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.paper import Paper
from app.models.idea_map import IdeaMap
from app.schemas.papers import PaperResponse, IdeaMapResponse
from app.jobs.queue import get_queue
from app.jobs.idea_map import generate_idea_map
from app.services.html_parser import prepare_arxiv_html_for_viewer
from app.services.paper_html_source import arxiv_html_url, read_local_paper_html

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

    local_html = read_local_paper_html(paper.arxiv_id)
    if local_html:
        return {
            "html": prepare_arxiv_html_for_viewer(
                local_html.html,
                local_html.source_url,
            ),
            "source_url": local_html.source_url,
        }

    return {
        "html": None,
        "source_url": arxiv_html_url(paper.arxiv_id) if paper.arxiv_id else None,
    }


@router.post("/{paper_id}/idea-map", response_model=IdeaMapResponse)
def create_or_get_idea_map(paper_id: str, db: Session = Depends(get_db)):
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    existing = db.query(IdeaMap).filter(IdeaMap.paper_id == paper_id).first()
    if existing:
        if existing.status in {"queued", "running", "claims_running", "warrants_running"}:
            return existing

        existing.status = "queued"
        existing.claims = []
        existing.dropped_reason = None
        existing.error = None
        existing.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(existing)
        return _enqueue_idea_map(existing, db)

    now = datetime.now(timezone.utc)
    idea_map = IdeaMap(
        id=str(uuid.uuid4()),
        paper_id=paper_id,
        status="queued",
        created_at=now,
        updated_at=now,
    )
    db.add(idea_map)
    db.commit()
    db.refresh(idea_map)

    return _enqueue_idea_map(idea_map, db)


def _enqueue_idea_map(idea_map: IdeaMap, db: Session) -> IdeaMap:
    try:
        q = get_queue()
        job = q.enqueue(generate_idea_map, idea_map.id)
        logger.info("enqueued idea map=%s job=%s", idea_map.id, getattr(job, "id", None))
    except Exception as exc:
        logger.exception("failed to enqueue idea map=%s", idea_map.id)
        idea_map.status = "failed"
        idea_map.error = f"Could not enqueue idea map generation: {exc}"
        idea_map.updated_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(status_code=503, detail=idea_map.error) from exc

    return idea_map


@router.get("/{paper_id}/idea-map", response_model=IdeaMapResponse)
def get_idea_map(paper_id: str, db: Session = Depends(get_db)):
    idea_map = db.query(IdeaMap).filter(IdeaMap.paper_id == paper_id).first()
    if not idea_map:
        raise HTTPException(status_code=404, detail="Idea map not found")
    return idea_map
