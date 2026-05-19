"""Tests for RQ queue routing by job kind."""

import uuid
from datetime import date, datetime, timezone

import pytest

from app.jobs.queues import (
    IDEA_MAPS,
    INTERACTIVE,
    KIND_TO_QUEUE,
    REPORTS,
    enqueue_for_job,
    queue_for_kind,
)
from app.models.idea_map import SQLAIdeaMap
from app.models.search_run import SQLASearchRun
from app.services.jobs import create_job
from paper_search_core.models.paper import SQLAPaper


@pytest.mark.parametrize("kind,expected", list(KIND_TO_QUEUE.items()))
def test_queue_for_kind(kind, expected):
    assert queue_for_kind(kind) == expected


def test_queue_for_kind_unknown_raises():
    with pytest.raises(ValueError, match="Unknown job kind"):
        queue_for_kind("not_a_real_kind")


def test_create_job_sets_queue_from_kind(db_session):
    job = create_job(
        db_session,
        kind="daily_search",
        subject_type="search_run",
        subject_id="run-1",
    )
    assert job.queue_name == REPORTS


def test_create_job_explicit_queue_name(db_session):
    job = create_job(
        db_session,
        kind="daily_search",
        subject_type="search_run",
        subject_id="run-1",
        queue_name="custom",
    )
    assert job.queue_name == "custom"


def test_enqueue_for_job_uses_matching_queue(db_session, monkeypatch):
    captured: list[str] = []

    class FakeQueue:
        def enqueue(self, *args, **kwargs):
            class FakeRqJob:
                id = "rq-test"

            return FakeRqJob()

    def fake_get_queue(name: str):
        captured.append(name)
        return FakeQueue()

    monkeypatch.setattr("app.jobs.queues.get_queue", fake_get_queue)

    job = create_job(
        db_session,
        kind="feedback_reflection",
        subject_type="feedback_batch",
        subject_id="batch",
    )

    def worker():
        pass

    enqueue_for_job(job, worker)
    assert captured == [INTERACTIVE]


def test_jobs_overview_active_and_recent(client, db_session):
    now = datetime.now(timezone.utc)
    run = SQLASearchRun(
        id=str(uuid.uuid4()),
        status="running",
        run_date=date(2026, 5, 19),
        created_at=now,
    )
    db_session.add(run)
    active_search = create_job(
        db_session,
        kind="daily_search",
        subject_type="search_run",
        subject_id=run.id,
        status="running",
    )
    active_feedback = create_job(
        db_session,
        kind="feedback_reflection",
        subject_type="feedback_batch",
        subject_id="batch",
        status="queued",
    )

    paper = SQLAPaper(
        id=str(uuid.uuid4()),
        title="Attention Is All You Need",
        source_type="arxiv",
        source_id="1706.03762",
        search_text="transformers",
        authors=["Vaswani"],
        created_at=now,
    )
    db_session.add(paper)
    db_session.flush()
    idea_map = SQLAIdeaMap(
        id=str(uuid.uuid4()),
        paper_id=paper.id,
        status="completed",
        created_at=now,
        updated_at=now,
    )
    db_session.add(idea_map)
    completed_idea_map = create_job(
        db_session,
        kind="idea_map",
        subject_type="idea_map",
        subject_id=idea_map.id,
        status="completed",
    )
    completed_idea_map.completed_at = now
    db_session.commit()

    resp = client.get("/jobs/overview")
    assert resp.status_code == 200
    payload = resp.json()

    assert len(payload["active"]) == 2
    active_by_kind = {entry["job"]["kind"]: entry for entry in payload["active"]}
    assert active_by_kind["daily_search"]["label"] == "Daily search"
    assert active_by_kind["daily_search"]["href"] == "/dashboard/daily/report"
    assert active_by_kind["daily_search"]["detail"] == "2026-05-19"
    assert active_by_kind["feedback_reflection"]["label"] == "Processing feedback"
    assert active_by_kind["feedback_reflection"]["href"] == "/dashboard/filters"

    assert len(payload["recent"]) >= 1
    recent_idea = next(
        entry for entry in payload["recent"] if entry["job"]["kind"] == "idea_map"
    )
    assert recent_idea["label"] == "Idea map"
    assert recent_idea["href"] == f"/dashboard/papers/{paper.id}"
    assert recent_idea["detail"] == "Attention Is All You Need"
