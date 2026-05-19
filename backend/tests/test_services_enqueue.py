from datetime import datetime, timezone

import pytest

from app.models.research_profile_import import SQLAResearchProfileImport
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
    assert job.completed_at is not None


def test_enqueue_dispatcher_import_failure_marks_failed(db_session, monkeypatch):
    job = create_job(
        db_session,
        kind="feedback_reflection",
        subject_type="feedback_batch",
        subject_id="1",
    )
    db_session.add(job)
    commit_refresh(db_session, job)

    def broken_dispatcher():
        raise ModuleNotFoundError("No module named 'backoff'")

    monkeypatch.setattr("app.services.jobs._dispatcher_run_job", broken_dispatcher)

    with pytest.raises(ConnectionError):
        enqueue(db_session, job)

    assert job.status == "failed"
    assert "backoff" in (job.error or "")
    assert job.completed_at is not None


def test_enqueue_failure_marks_scholar_import_failed(db_session, monkeypatch):
    now = datetime.now(timezone.utc)
    profile_import = SQLAResearchProfileImport(
        status="pending",
        source_type="semantic_scholar",
        source_url="https://www.semanticscholar.org/author/test",
        external_author_id="123",
        display_name="Test Author",
        created_at=now,
        updated_at=now,
    )
    db_session.add(profile_import)
    db_session.flush()
    job = create_job(
        db_session,
        kind="scholar_import",
        subject_type="research_profile_import",
        subject_id=profile_import.id,
    )
    db_session.add(job)
    commit_refresh(db_session, profile_import, job)

    def broken_dispatcher():
        raise ModuleNotFoundError("No module named 'backoff'")

    monkeypatch.setattr("app.services.jobs._dispatcher_run_job", broken_dispatcher)

    with pytest.raises(ConnectionError):
        enqueue(db_session, job)

    db_session.refresh(profile_import)
    assert job.status == "failed"
    assert "backoff" in (job.error or "")
    assert profile_import.status == "failed"
    assert "backoff" in (profile_import.error or "")


def test_start_daily_search_validation(db_session, monkeypatch):
    monkeypatch.setattr(
        "app.services.search_runs.enabled_source_types", lambda db: set()
    )
    with pytest.raises(ValueError, match="No data sources are enabled"):
        search_runs.start_daily_search(db_session)
