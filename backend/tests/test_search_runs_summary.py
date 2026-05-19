import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.filter import SQLAFilter
from app.models.job import SQLAJob
from app.models.search_run import SQLASearchRun
from app.services import search_runs
from app.services.jobs import SUMMARY_JOB_MAX_SECONDS, reconcile_stale_job


@pytest.fixture
def completed_search_run(db_session):
    run_id = str(uuid.uuid4())
    run = SQLASearchRun(
        id=run_id,
        status="running",
        run_date=datetime.now(timezone.utc).date(),
        match_count=1,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    search_job = SQLAJob(
        id=str(uuid.uuid4()),
        kind="daily_search",
        status="completed",
        subject_type="search_run",
        subject_id=run_id,
        queue_name="reports",
        payload={},
        progress={},
        created_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    db_session.add(search_job)
    db_session.commit()
    return run, search_job


def test_start_daily_summary_returns_existing_active_job(
    db_session, completed_search_run, monkeypatch
):
    run, _search_job = completed_search_run
    enqueued: list[str] = []

    def fake_enqueue(db, job, **kwargs):
        enqueued.append(job.id)

    monkeypatch.setattr(search_runs, "enqueue", fake_enqueue)

    first = search_runs.start_daily_summary(db_session, run.id)
    second = search_runs.start_daily_summary(db_session, run.id)

    assert first.id == second.id
    assert len(enqueued) == 1


def test_search_run_payload_includes_active_summary_job_id(db_session):
    run_id = str(uuid.uuid4())
    run = SQLASearchRun(
        id=run_id,
        status="running",
        run_date=datetime.now(timezone.utc).date(),
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    summary_job = SQLAJob(
        id=str(uuid.uuid4()),
        kind="daily_search_summary",
        status="running",
        subject_type="search_run",
        subject_id=run_id,
        queue_name="reports",
        payload={},
        progress={},
        created_at=datetime.now(timezone.utc),
        started_at=datetime.now(timezone.utc),
    )
    db_session.add(summary_job)
    db_session.commit()

    payload = search_runs.search_run_payload(db_session, run)

    assert payload.summary_job_id == summary_job.id


def test_reconcile_stale_summary_job_marks_job_and_run_failed(db_session):
    run_id = str(uuid.uuid4())
    run = SQLASearchRun(
        id=run_id,
        status="running",
        run_date=datetime.now(timezone.utc).date(),
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(run)
    stale_started = datetime.now(timezone.utc) - timedelta(
        seconds=SUMMARY_JOB_MAX_SECONDS + 60
    )
    job = SQLAJob(
        id=str(uuid.uuid4()),
        kind="daily_search_summary",
        status="running",
        subject_type="search_run",
        subject_id=run_id,
        queue_name="reports",
        payload={},
        progress={},
        created_at=stale_started,
        started_at=stale_started,
    )
    db_session.add(job)
    db_session.commit()

    assert reconcile_stale_job(db_session, job) is True

    assert job.status == "failed"
    assert job.to_pydantic().status == "failed"
    db_session.refresh(run)
    assert job.error == "Job timed out"
    assert run.status == "failed"
    assert run.error == "Job timed out"
