from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.filter import Filter
from app.services import filters as filter_service

router = APIRouter(prefix="/filters", tags=["filters"])


class FilterDefinition(BaseModel):
    name: str
    description: str
    mode: Literal["claim", "topic"] = "topic"


class FilterCreate(BaseModel):
    name: str
    definition: FilterDefinition


class FilterUpdate(BaseModel):
    name: Optional[str] = None
    definition: Optional[FilterDefinition] = None


@router.get("", response_model=list[Filter])
def list_filters(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    return [
        filter.to_pydantic()
        for filter in filter_service.list_filters(db, status=status)
    ]


@router.post("", response_model=Filter)
def create_filter(body: FilterCreate, db: Session = Depends(get_db)):
    filter = filter_service.create_filter(db, body)
    return filter.to_pydantic()


@router.patch("/{filter_id}", response_model=Filter)
def update_filter(filter_id: str, body: FilterUpdate, db: Session = Depends(get_db)):
    try:
        filter = filter_service.update_filter(db, filter_id, body)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return filter.to_pydantic()


@router.post("/{filter_id}/archive", response_model=Filter)
def archive_filter(filter_id: str, db: Session = Depends(get_db)):
    try:
        filter = filter_service.archive_filter(db, filter_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return filter.to_pydantic()


@router.post("/{filter_id}/restore", response_model=Filter)
def restore_filter(filter_id: str, db: Session = Depends(get_db)):
    try:
        filter = filter_service.restore_filter(db, filter_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return filter.to_pydantic()


@router.post("/{filter_id}/accept", response_model=Filter)
def accept_proposal(filter_id: str, db: Session = Depends(get_db)):
    try:
        filter = filter_service.accept_proposal(db, filter_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return filter.to_pydantic()


@router.post("/{filter_id}/reject", response_model=Filter)
def reject_proposal(filter_id: str, db: Session = Depends(get_db)):
    try:
        filter = filter_service.reject_proposal(db, filter_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return filter.to_pydantic()
