import pytest

from app.models.job import SQLAJob
from app.services.errors import EnqueueFailed, ValidationFailed
from app.services.job_enqueue import enqueue_job, persist_then_enqueue
from app.services.jobs import create_job
from app.services import search_runs


def test_enqueue_job_success(db_session, monkeypatch):
    job = create_job(
        db_session,
        kind="feedback_reflection",
        subject_type="feedback_batch",
        subject_id="1",
    )
    db_session.commit()

    class FakeRqJob:
        id = "rq-123"

    enqueue_job(
        db_session,
        job=job,
        enqueue=lambda: FakeRqJob(),
    )
    assert job.queue_job_id == "rq-123"


def test_enqueue_job_failure_marks_failed(db_session):
    job = create_job(
        db_session,
        kind="feedback_reflection",
        subject_type="feedback_batch",
        subject_id="1",
    )
    db_session.commit()

    with pytest.raises(EnqueueFailed):
        enqueue_job(
            db_session,
            job=job,
            enqueue=lambda: (_ for _ in ()).throw(RuntimeError("queue down")),
        )
    assert job.status == "failed"
    assert "queue down" in (job.error or "")


def test_start_daily_search_validation(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.services.search_runs.enabled_source_types", lambda db: set()
    )
    with pytest.raises(ValidationFailed, match="No data sources are enabled"):
        search_runs.start_daily_search(db_session)


def test_persist_then_enqueue_commits_entities(db_session, monkeypatch):
    job = create_job(
        db_session,
        kind="feedback_reflection",
        subject_type="feedback_batch",
        subject_id="x",
    )
    db_session.add(job)

    class FakeRqJob:
        id = "rq-456"

    persist_then_enqueue(
        db_session,
        job=job,
        entities=(),
        enqueue=lambda: FakeRqJob(),
        on_failure=lambda sess, err: None,
    )
    refreshed = db_session.query(SQLAJob).filter(SQLAJob.id == job.id).first()
    assert refreshed is not None
    assert refreshed.queue_job_id == "rq-456"
