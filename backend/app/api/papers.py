import uuid
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.paper import Paper
from app.models.paper_html import PaperHtml
from app.models.idea_map import IdeaMap
from app.schemas.papers import PaperResponse, IdeaMapResponse
from app.jobs.queue import get_queue
from app.jobs.idea_map import generate_idea_map

router = APIRouter(prefix="/papers", tags=["papers"])


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

    cached = db.query(PaperHtml).filter(PaperHtml.paper_id == paper_id).first()
    if cached:
        return {"html": cached.html, "source_url": cached.source_url}

    return {"html": None, "source_url": f"https://arxiv.org/html/{paper.arxiv_id}" if paper.arxiv_id else None}


@router.post("/{paper_id}/idea-map", response_model=IdeaMapResponse)
def create_or_get_idea_map(paper_id: str, db: Session = Depends(get_db)):
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    existing = db.query(IdeaMap).filter(IdeaMap.paper_id == paper_id).first()
    if existing:
        return existing

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

    try:
        q = get_queue()
        q.enqueue(generate_idea_map, idea_map.id)
    except Exception:
        threading.Thread(
            target=generate_idea_map,
            args=(idea_map.id,),
            daemon=True,
        ).start()

    return idea_map


@router.get("/{paper_id}/idea-map", response_model=IdeaMapResponse)
def get_idea_map(paper_id: str, db: Session = Depends(get_db)):
    idea_map = db.query(IdeaMap).filter(IdeaMap.paper_id == paper_id).first()
    if not idea_map:
        raise HTTPException(status_code=404, detail="Idea map not found")
    return idea_map
