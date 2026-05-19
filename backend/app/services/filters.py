from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.models.filter import SQLAFilter
from app.services.errors import NotFound, ValidationFailed

if TYPE_CHECKING:
    from app.api.filters import FilterCreate, FilterUpdate


def list_filters(db: Session, *, status: str | None = None) -> list[SQLAFilter]:
    query = db.query(SQLAFilter)
    if status:
        query = query.filter(SQLAFilter.status == status)
    return query.order_by(SQLAFilter.created_at.desc()).all()


def list_active_filters(db: Session) -> list[SQLAFilter]:
    return db.query(SQLAFilter).filter(SQLAFilter.status == "active").all()


def get_filter(db: Session, filter_id: str) -> SQLAFilter:
    filt = db.query(SQLAFilter).filter(SQLAFilter.id == filter_id).first()
    if not filt:
        raise NotFound("Filter not found")
    return filt


def create_filter(db: Session, body: FilterCreate) -> SQLAFilter:
    now = datetime.now(timezone.utc)
    filt = SQLAFilter(
        id=str(uuid.uuid4()),
        name=body.name,
        definition=body.definition.model_dump(),
        status="active",
        created_at=now,
        updated_at=now,
    )
    db.add(filt)
    db.flush()
    db.refresh(filt)
    return filt


def update_filter(db: Session, filter_id: str, body: FilterUpdate) -> SQLAFilter:
    filt = get_filter(db, filter_id)
    if body.name is not None:
        filt.name = body.name
    if body.definition is not None:
        filt.definition = body.definition.model_dump()
        filt.name = body.definition.name
    filt.updated_at = datetime.now(timezone.utc)
    db.flush()
    db.refresh(filt)
    return filt


def archive_filter(db: Session, filter_id: str) -> SQLAFilter:
    filt = get_filter(db, filter_id)
    now = datetime.now(timezone.utc)
    filt.status = "archived"
    filt.archived_at = now
    filt.updated_at = now
    db.flush()
    db.refresh(filt)
    return filt


def restore_filter(db: Session, filter_id: str) -> SQLAFilter:
    filt = get_filter(db, filter_id)
    filt.status = "active"
    filt.archived_at = None
    filt.updated_at = datetime.now(timezone.utc)
    db.flush()
    db.refresh(filt)
    return filt


def accept_proposal(db: Session, filter_id: str) -> SQLAFilter:
    filt = get_filter(db, filter_id)
    now = datetime.now(timezone.utc)

    if filt.proposed_action == "create":
        filt.status = "active"
        filt.proposed_action = None
        filt.updated_at = now
    elif filt.proposed_action == "revise" and filt.target_filter_id:
        target = (
            db.query(SQLAFilter).filter(SQLAFilter.id == filt.target_filter_id).first()
        )
        if target:
            target.definition = dict(filt.definition or {})
            target.name = filt.name
            target.updated_at = now
        filt.status = "archived"
        filt.archived_at = now
        filt.updated_at = now
    elif filt.proposed_action == "delete" and filt.target_filter_id:
        target = (
            db.query(SQLAFilter).filter(SQLAFilter.id == filt.target_filter_id).first()
        )
        if target:
            target.status = "archived"
            target.archived_at = now
            target.updated_at = now
        filt.status = "archived"
        filt.archived_at = now
        filt.updated_at = now
    else:
        raise ValidationFailed("Not a pending proposal")

    db.flush()
    db.refresh(filt)
    return filt


def reject_proposal(db: Session, filter_id: str) -> SQLAFilter:
    filt = get_filter(db, filter_id)
    if not filt.proposed_action:
        raise ValidationFailed("Not a pending proposal")
    now = datetime.now(timezone.utc)
    filt.status = "archived"
    filt.archived_at = now
    filt.updated_at = now
    db.flush()
    db.refresh(filt)
    return filt
