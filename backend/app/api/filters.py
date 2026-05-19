from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.http_errors import raise_http_from_service
from app.db.session import get_db
from app.schemas.filters import FilterCreate, FilterUpdate, FilterResponse
from app.services import filters as filter_service

router = APIRouter(prefix="/filters", tags=["filters"])


@router.get("", response_model=list[FilterResponse])
def list_filters(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    return [filt.to_pydantic() for filt in filter_service.list_filters(db, status=status)]


@router.post("", response_model=FilterResponse)
def create_filter(body: FilterCreate, db: Session = Depends(get_db)):
    filt = filter_service.create_filter(db, body)
    return filt.to_pydantic()


@router.patch("/{filter_id}", response_model=FilterResponse)
def update_filter(filter_id: str, body: FilterUpdate, db: Session = Depends(get_db)):
    try:
        filt = filter_service.update_filter(db, filter_id, body)
    except Exception as exc:
        raise_http_from_service(exc)
    return filt.to_pydantic()


@router.post("/{filter_id}/archive", response_model=FilterResponse)
def archive_filter(filter_id: str, db: Session = Depends(get_db)):
    try:
        filt = filter_service.archive_filter(db, filter_id)
    except Exception as exc:
        raise_http_from_service(exc)
    return filt.to_pydantic()


@router.post("/{filter_id}/restore", response_model=FilterResponse)
def restore_filter(filter_id: str, db: Session = Depends(get_db)):
    try:
        filt = filter_service.restore_filter(db, filter_id)
    except Exception as exc:
        raise_http_from_service(exc)
    return filt.to_pydantic()


@router.post("/{filter_id}/accept", response_model=FilterResponse)
def accept_proposal(filter_id: str, db: Session = Depends(get_db)):
    try:
        filt = filter_service.accept_proposal(db, filter_id)
    except Exception as exc:
        raise_http_from_service(exc)
    return filt.to_pydantic()


@router.post("/{filter_id}/reject", response_model=FilterResponse)
def reject_proposal(filter_id: str, db: Session = Depends(get_db)):
    try:
        filt = filter_service.reject_proposal(db, filter_id)
    except Exception as exc:
        raise_http_from_service(exc)
    return filt.to_pydantic()
