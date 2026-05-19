import uuid
from datetime import datetime, timezone

import pytest

from app.models.idea_map import SQLAIdeaMap
from paper_search_core.models.paper import SQLAPaper
from app.services import papers as papers_service
from app.services.jobs import create_job


def _paper(db_session) -> SQLAPaper:
    now = datetime.now(timezone.utc)
    paper = SQLAPaper(
        id=str(uuid.uuid4()),
        title="Test Paper",
        source_type="arxiv",
        source_id="1234.5678",
        search_text="Test abstract.",
        authors=["Author"],
        created_at=now,
    )
    db_session.add(paper)
    db_session.flush()
    return paper


def test_start_idea_map_creates_new(db_session, monkeypatch):
    paper = _paper(db_session)

    class FakeQueue:
        def enqueue(self, *args, **kwargs):
            class FakeJob:
                id = "rq-idea"

            return FakeJob()

    monkeypatch.setattr("app.services.jobs.Queue", lambda *args, **kwargs: FakeQueue())
    monkeypatch.setattr("app.services.jobs.Redis.from_url", lambda url: object())

    job_id = papers_service.start_idea_map(db_session, paper.id)
    assert job_id
    idea_map = (
        db_session.query(SQLAIdeaMap).filter(SQLAIdeaMap.paper_id == paper.id).first()
    )
    assert idea_map is not None
    assert idea_map.status == "queued"


def test_start_idea_map_in_flight_returns_existing_job(db_session, monkeypatch):
    paper = _paper(db_session)
    now = datetime.now(timezone.utc)
    idea_map = SQLAIdeaMap(
        id=str(uuid.uuid4()),
        paper_id=paper.id,
        status="running",
        created_at=now,
        updated_at=now,
    )
    db_session.add(idea_map)
    job = create_job(
        db_session,
        kind="idea_map",
        subject_type="idea_map",
        subject_id=idea_map.id,
        status="running",
    )
    db_session.commit()

    job_id = papers_service.start_idea_map(db_session, paper.id)
    assert job_id == job.id


def test_get_paper_not_found(db_session):
    with pytest.raises(LookupError):
        papers_service.get_paper(db_session, "missing")


def test_serialize_idea_map_warrant_progress_uses_completed_tasks(db_session):
    paper = _paper(db_session)
    now = datetime.now(timezone.utc)
    idea_map = SQLAIdeaMap(
        id=str(uuid.uuid4()),
        paper_id=paper.id,
        status="warrants_running",
        claims=[
            {"id": "c1", "text": "Claim 1", "warrants": []},
            {"id": "c2", "text": "Claim 2", "warrants": []},
            {"id": "c3", "text": "Claim 3", "warrants": []},
        ],
        created_at=now,
        updated_at=now,
    )
    db_session.add(idea_map)
    job = create_job(
        db_session,
        kind="idea_map",
        subject_type="idea_map",
        subject_id=idea_map.id,
        status="running",
        progress={"current": 1, "total": 3},
    )
    db_session.commit()

    payload = papers_service.serialize_idea_map_job(db_session, job, idea_map)

    assert payload.progress == {"current": 1, "total": 3}
