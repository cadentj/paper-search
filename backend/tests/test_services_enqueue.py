import pytest

from app.models.job import SQLAJob
from app.services.jobs import commit_refresh, create_job, enqueue
from app.services import search_runs


def test_enqueue_success(db_session, monkeypatch):
    job = create_job(
        db_session,
        kind="feedback_reflection",
        subject_type="feedback_batch",
        subject_id="1",
    )
    db_session.add(job)

    enqueued: list[str] = []

    class FakeQueue:
        def enqueue(self, func, job_id):
            enqueued.append(job_id)

    monkeypatch.setattr(
        "app.services.jobs.Queue",
        lambda *args, **kwargs: FakeQueue(),
    )
    monkeypatch.setattr(
        "app.services.jobs.Redis.from_url",
        lambda url: object(),
    )

    commit_refresh(db_session, job)
    enqueue(db_session, job)
    assert enqueued == [job.id]
    assert job.status == "queued"


def test_enqueue_failure_marks_failed(db_session, monkeypatch):
    job = create_job(
        db_session,
        kind="feedback_reflection",
        subject_type="feedback_batch",
        subject_id="1",
    )
    db_session.add(job)
    commit_refresh(db_session, job)

    class FakeQueue:
        def enqueue(self, *args, **kwargs):
            raise RuntimeError("queue down")

    monkeypatch.setattr(
        "app.services.jobs.Queue",
        lambda *args, **kwargs: FakeQueue(),
    )
    monkeypatch.setattr(
        "app.services.jobs.Redis.from_url",
        lambda url: object(),
    )

    with pytest.raises(ConnectionError):
        enqueue(db_session, job)
    assert job.status == "failed"
    assert "queue down" in (job.error or "")


def test_start_daily_search_validation(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.services.search_runs.enabled_source_types", lambda db: set()
    )
    with pytest.raises(ValueError, match="No data sources are enabled"):
        search_runs.start_daily_search(db_session)
