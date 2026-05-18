import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.filter import Filter
from app.schemas.filters import FilterCreate, FilterUpdate, FilterResponse

router = APIRouter(prefix="/filters", tags=["filters"])


@router.get("", response_model=list[FilterResponse])
def list_filters(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(Filter)
    if status:
        query = query.filter(Filter.status == status)
    query = query.order_by(Filter.created_at.desc())
    return [filt.to_pydantic() for filt in query.all()]


@router.post("", response_model=FilterResponse)
def create_filter(body: FilterCreate, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    filt = Filter(
        id=str(uuid.uuid4()),
        name=body.name,
        definition=body.definition.model_dump(),
        status="active",
        created_at=now,
        updated_at=now,
    )
    db.add(filt)
    db.commit()
    db.refresh(filt)
    return filt.to_pydantic()


@router.patch("/{filter_id}", response_model=FilterResponse)
def update_filter(filter_id: str, body: FilterUpdate, db: Session = Depends(get_db)):
    filt = db.query(Filter).filter(Filter.id == filter_id).first()
    if not filt:
        raise HTTPException(status_code=404, detail="Filter not found")

    if body.name is not None:
        filt.name = body.name
    if body.definition is not None:
        filt.definition = body.definition.model_dump()
        filt.name = body.definition.name

    filt.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(filt)
    return filt.to_pydantic()


@router.post("/{filter_id}/archive", response_model=FilterResponse)
def archive_filter(filter_id: str, db: Session = Depends(get_db)):
    filt = db.query(Filter).filter(Filter.id == filter_id).first()
    if not filt:
        raise HTTPException(status_code=404, detail="Filter not found")

    filt.status = "archived"
    filt.archived_at = datetime.now(timezone.utc)
    filt.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(filt)
    return filt.to_pydantic()


@router.post("/{filter_id}/restore", response_model=FilterResponse)
def restore_filter(filter_id: str, db: Session = Depends(get_db)):
    filt = db.query(Filter).filter(Filter.id == filter_id).first()
    if not filt:
        raise HTTPException(status_code=404, detail="Filter not found")

    filt.status = "active"
    filt.archived_at = None
    filt.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(filt)
    return filt.to_pydantic()
