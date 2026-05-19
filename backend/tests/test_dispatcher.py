import pytest

from app.jobs.dispatcher import HANDLERS, run_job
from app.models.job import SQLAJob
from app.services.jobs import create_job, set_job_status


def test_unknown_kind_marks_failed(db_session):
    job = create_job(
        db_session,
        kind="not_a_real_kind",
        subject_type="test",
        subject_id="1",
        queue_name="interactive",
    )
    db_session.commit()

    assert HANDLERS.get(job.kind) is None
    set_job_status(job, status="failed", error=f"Unknown job kind: {job.kind}")
    db_session.commit()

    refreshed = db_session.get(SQLAJob, job.id)
    assert refreshed is not None
    assert refreshed.status == "failed"
    assert "Unknown job kind" in (refreshed.error or "")


def test_run_job_invokes_handler(test_database, patch_worker_database):
    with test_database.session() as db:
        job = create_job(
            db,
            kind="feedback_reflection",
            subject_type="feedback_batch",
            subject_id="batch",
        )
        job_id = job.id

    called: list[str] = []

    def fake_run(db, job_row):
        called.append(job_row.id)

    original = HANDLERS["feedback_reflection"]
    HANDLERS["feedback_reflection"] = fake_run
    try:
        run_job(job_id)
    finally:
        HANDLERS["feedback_reflection"] = original

    assert called == [job_id]


def test_run_job_unknown_kind_via_entrypoint(test_database, patch_worker_database):
    with test_database.session() as db:
        job = create_job(
            db,
            kind="not_a_real_kind",
            subject_type="test",
            subject_id="1",
            queue_name="interactive",
        )
        job_id = job.id

    run_job(job_id)

    with test_database.session() as db:
        refreshed = db.get(SQLAJob, job_id)
        assert refreshed is not None
        assert refreshed.status == "failed"
        assert "Unknown job kind" in (refreshed.error or "")
