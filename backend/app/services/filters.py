from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy.orm import Session

from app.models.filter import SQLAFilter


class _FilterDefinitionInput(Protocol):
    name: str

    def model_dump(self) -> dict:
        pass


class _FilterCreateInput(Protocol):
    name: str
    definition: _FilterDefinitionInput


class _FilterUpdateInput(Protocol):
    name: str | None
    definition: _FilterDefinitionInput | None


def list_filters(db: Session, status: str | None = None) -> list[SQLAFilter]:
    query = db.query(SQLAFilter)
    if status:
        query = query.filter(SQLAFilter.status == status)
    return query.order_by(SQLAFilter.created_at.desc()).all()


def get_filter(db: Session, filter_id: str) -> SQLAFilter:
    filter = db.query(SQLAFilter).filter(SQLAFilter.id == filter_id).first()
    if not filter:
        raise LookupError("Filter not found")
    return filter


def create_filter(db: Session, body: _FilterCreateInput) -> SQLAFilter:
    now = datetime.now(timezone.utc)
    filter = SQLAFilter(
        id=str(uuid.uuid4()),
        name=body.name,
        definition=body.definition.model_dump(),
        status="active",
        created_at=now,
        updated_at=now,
    )
    db.add(filter)
    db.flush()
    db.refresh(filter)
    return filter


def update_filter(db: Session, filter_id: str, body: _FilterUpdateInput) -> SQLAFilter:
    filter = get_filter(db, filter_id)
    if body.name is not None:
        filter.name = body.name
    if body.definition is not None:
        filter.definition = body.definition.model_dump()
        filter.name = body.definition.name
    filter.updated_at = datetime.now(timezone.utc)
    db.flush()
    db.refresh(filter)
    return filter


def archive_filter(db: Session, filter_id: str) -> SQLAFilter:
    filter = get_filter(db, filter_id)
    now = datetime.now(timezone.utc)
    filter.status = "archived"
    filter.archived_at = now
    filter.updated_at = now
    db.flush()
    db.refresh(filter)
    return filter


def restore_filter(db: Session, filter_id: str) -> SQLAFilter:
    filter = get_filter(db, filter_id)
    filter.status = "active"
    filter.archived_at = None
    filter.updated_at = datetime.now(timezone.utc)
    db.flush()
    db.refresh(filter)
    return filter


def accept_proposal(db: Session, filter_id: str) -> SQLAFilter:
    filter = get_filter(db, filter_id)
    now = datetime.now(timezone.utc)

    if filter.proposed_action == "create":
        filter.status = "active"
        filter.proposed_action = None
        filter.updated_at = now
    elif filter.proposed_action == "revise" and filter.target_filter_id:
        target = (
            db.query(SQLAFilter)
            .filter(SQLAFilter.id == filter.target_filter_id)
            .first()
        )
        if target:
            target.definition = dict(filter.definition or {})
            target.name = filter.name
            target.updated_at = now
        filter.status = "archived"
        filter.archived_at = now
        filter.updated_at = now
    elif filter.proposed_action == "delete" and filter.target_filter_id:
        target = (
            db.query(SQLAFilter)
            .filter(SQLAFilter.id == filter.target_filter_id)
            .first()
        )
        if target:
            target.status = "archived"
            target.archived_at = now
            target.updated_at = now
        filter.status = "archived"
        filter.archived_at = now
        filter.updated_at = now
    else:
        raise ValueError("Not a pending proposal")

    db.flush()
    db.refresh(filter)
    return filter


def reject_proposal(db: Session, filter_id: str) -> SQLAFilter:
    filter = get_filter(db, filter_id)
    if not filter.proposed_action:
        raise ValueError("Not a pending proposal")
    now = datetime.now(timezone.utc)
    filter.status = "archived"
    filter.archived_at = now
    filter.updated_at = now
    db.flush()
    db.refresh(filter)
    return filter
