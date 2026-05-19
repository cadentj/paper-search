import uuid
from datetime import datetime, timezone

import pytest

from app.models.filter import SQLAFilter
from app.services import filters as filter_service


def _proposal_filter(
    db_session, *, action: str, target_id: str | None = None
) -> SQLAFilter:
    now = datetime.now(timezone.utc)
    filter = SQLAFilter(
        id=str(uuid.uuid4()),
        name="Proposal",
        definition={"name": "Proposal", "description": "", "mode": "topic"},
        status="pending_create",
        proposed_action=action,
        target_filter_id=target_id,
        created_at=now,
        updated_at=now,
    )
    db_session.add(filter)
    db_session.flush()
    return filter


def test_accept_proposal_create(db_session):
    filter = _proposal_filter(db_session, action="create")
    result = filter_service.accept_proposal(db_session, filter.id)
    assert result.status == "active"
    assert result.proposed_action is None


def test_accept_proposal_revise(db_session):
    target = SQLAFilter(
        id=str(uuid.uuid4()),
        name="Target",
        definition={"name": "Target", "description": "old", "mode": "topic"},
        status="active",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(target)
    db_session.flush()
    filter = _proposal_filter(db_session, action="revise", target_id=target.id)
    filter.definition = {"name": "Revised", "description": "new", "mode": "topic"}
    filter.name = "Revised"
    db_session.flush()

    filter_service.accept_proposal(db_session, filter.id)
    db_session.refresh(target)
    assert target.name == "Revised"
    assert filter.status == "archived"


def test_accept_proposal_invalid(db_session):
    filter = _proposal_filter(db_session, action="create")
    filter.proposed_action = None
    db_session.flush()
    with pytest.raises(ValueError):
        filter_service.accept_proposal(db_session, filter.id)
