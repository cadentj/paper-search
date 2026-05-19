import uuid
from datetime import datetime, timezone

import pytest

from app.models.filter import SQLAFilter
from app.services.errors import ValidationFailed
from app.services import filters as filter_service


def _proposal_filter(db_session, *, action: str, target_id: str | None = None) -> SQLAFilter:
    now = datetime.now(timezone.utc)
    filt = SQLAFilter(
        id=str(uuid.uuid4()),
        name="Proposal",
        definition={"name": "Proposal", "description": "", "mode": "topic"},
        status="pending_create",
        proposed_action=action,
        target_filter_id=target_id,
        created_at=now,
        updated_at=now,
    )
    db_session.add(filt)
    db_session.flush()
    return filt


def test_accept_proposal_create(db_session):
    filt = _proposal_filter(db_session, action="create")
    result = filter_service.accept_proposal(db_session, filt.id)
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
    filt = _proposal_filter(db_session, action="revise", target_id=target.id)
    filt.definition = {"name": "Revised", "description": "new", "mode": "topic"}
    filt.name = "Revised"
    db_session.flush()

    filter_service.accept_proposal(db_session, filt.id)
    db_session.refresh(target)
    assert target.name == "Revised"
    assert filt.status == "archived"


def test_accept_proposal_invalid(db_session):
    filt = _proposal_filter(db_session, action="create")
    filt.proposed_action = None
    db_session.flush()
    with pytest.raises(ValidationFailed):
        filter_service.accept_proposal(db_session, filt.id)
