"""Backend API integration tests."""

from datetime import date, datetime, timezone

import pytest

from app.models.filter import SQLAFilter
from app.models.paper_match import SQLAPaperMatch
from app.models.paper_match_feedback import SQLAPaperMatchFeedback
from app.models.paper_note import SQLAPaperNote
from app.models.search_run import SQLASearchRun
from paper_search_core.models.paper import SQLAPaper


class NoopQueue:
    def enqueue(self, *args, **kwargs):
        return None


class TestOnboarding:
    @pytest.fixture(autouse=True)
    def _mock_queue(self, monkeypatch):
        monkeypatch.setattr("app.jobs.queues.get_queue", lambda _name: NoopQueue())

    def test_onboarding_extraction_and_completion_flow(self, client):
        resp = client.get("/onboarding/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["completed"] is False
        assert data["active_filter_count"] == 0

        resp = client.post(
            "/onboarding/extractions",
            json={"input_text": "I study mechanistic interpretability"},
        )
        assert resp.status_code == 200
        data = resp.json()
        job_id = data["job_id"]
        job = client.get(f"/jobs/{job_id}").json()
        ext_id = job["subject_id"]
        assert job["status"] in ("queued", "running", "completed", "failed")

        ext = client.get(f"/onboarding/extractions/{ext_id}").json()
        assert ext["status"] in ("queued", "running", "completed", "failed")
        assert ext["input_text"] == "I study mechanistic interpretability"

        resp2 = client.get(f"/onboarding/extractions/{ext_id}")
        assert resp2.status_code == 200
        assert resp2.json()["id"] == ext_id

        missing = client.get("/onboarding/extractions/nonexistent-id")
        assert missing.status_code == 404

        filters_payload = [
            {
                "name": "Test Filter",
                "definition": {
                    "name": "Test Filter",
                    "description": "Test statement",
                    "mode": "claim",
                },
            }
        ]
        resp = client.post("/onboarding/complete", json={"filters": filters_payload})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Test Filter"
        assert data[0]["status"] == "active"

        status = client.get("/onboarding/status").json()
        assert status["completed"] is True
        assert status["active_filter_count"] == 1

    def test_create_extraction_fails_fast_when_queue_unavailable(
        self, client, monkeypatch
    ):
        def broken_queue():
            raise RuntimeError("redis unavailable")

        monkeypatch.setattr("app.jobs.queues.get_queue", broken_queue)
        resp = client.post(
            "/onboarding/extractions",
            json={"input_text": "I study mechanistic interpretability"},
        )
        assert resp.status_code == 503
        assert "redis unavailable" in resp.text


class TestFilters:
    def _create_filter(self, client, name="My Filter"):
        return client.post(
            "/filters",
            json={
                "name": name,
                "definition": {
                    "name": name,
                    "description": "Test",
                    "mode": "claim",
                },
            },
        )

    def test_filter_lifecycle(self, client):
        resp = self._create_filter(client, "Filter A")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Filter A"
        assert data["status"] == "active"

        self._create_filter(client, "Filter B")
        resp = client.get("/filters")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

        fid = data["id"]
        resp = client.patch(
            f"/filters/{fid}",
            json={"name": "Updated Name"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"

        resp = client.post(f"/filters/{fid}/archive")
        assert resp.status_code == 200
        assert resp.json()["status"] == "archived"
        assert resp.json()["archived_at"] is not None

        resp = client.post(f"/filters/{fid}/restore")
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"
        assert resp.json()["archived_at"] is None

        resp = client.post("/filters/nonexistent/archive")
        assert resp.status_code == 404


class TestFeedback:
    def _seed_feedback_context(self, db_session):
        now = datetime.now(timezone.utc)
        paper = SQLAPaper(
            id="paper-1",
            source_type="arxiv",
            source_id="2605.00001",
            title="Visible Feedback Paper",
            search_text="Abstract",
            authors=["Author"],
            created_at=now,
        )
        unmatched_paper = SQLAPaper(
            id="paper-2",
            source_type="arxiv",
            source_id="2605.00002",
            title="Unmatched Feedback Paper",
            search_text="Abstract",
            authors=[],
            created_at=now,
        )
        processed_paper = SQLAPaper(
            id="paper-3",
            source_type="arxiv",
            source_id="2605.00003",
            title="Processed Feedback Paper",
            search_text="Abstract",
            authors=[],
            created_at=now,
        )
        filter = SQLAFilter(
            id="filter-1",
            name="Relevant Filter",
            definition={
                "name": "Relevant Filter",
                "description": "Test",
                "mode": "topic",
            },
            status="active",
            created_at=now,
            updated_at=now,
        )
        search_run = SQLASearchRun(
            id="run-1",
            status="completed",
            run_date=date.today(),
            created_at=now,
        )
        db_session.add_all(
            [paper, unmatched_paper, processed_paper, filter, search_run]
        )
        db_session.flush()

        match = SQLAPaperMatch(
            id="match-1",
            search_run_id=search_run.id,
            filter_id=filter.id,
            paper_id=paper.id,
            result={"reason": "Relevant"},
            created_at=now,
        )
        db_session.add(match)
        db_session.flush()
        db_session.add_all(
            [
                SQLAPaperMatchFeedback(
                    id="feedback-1",
                    paper_match_id=match.id,
                    search_run_id=search_run.id,
                    filter_id=filter.id,
                    paper_id=paper.id,
                    value="down",
                    processed=False,
                    created_at=now,
                    updated_at=now,
                ),
                SQLAPaperMatchFeedback(
                    id="feedback-2",
                    paper_id=unmatched_paper.id,
                    value="up",
                    processed=False,
                    created_at=now,
                    updated_at=now,
                ),
                SQLAPaperMatchFeedback(
                    id="feedback-processed",
                    paper_id=processed_paper.id,
                    value="up",
                    processed=True,
                    created_at=now,
                    updated_at=now,
                ),
                SQLAPaperNote(
                    id="note-1",
                    paper_id=paper.id,
                    text="This should inform the filter.",
                    processed=False,
                    created_at=now,
                    updated_at=now,
                ),
                SQLAPaperNote(
                    id="note-processed",
                    paper_id=processed_paper.id,
                    text="Already handled",
                    processed=True,
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        db_session.commit()

    def test_pending_feedback_items_include_votes_and_notes(self, client, db_session):
        self._seed_feedback_context(db_session)

        resp = client.get("/feedback/items?status=pending")

        assert resp.status_code == 200
        items = resp.json()
        assert {item["id"] for item in items} == {
            "feedback-1",
            "feedback-2",
            "note-1",
        }

        matched_vote = next(item for item in items if item["id"] == "feedback-1")
        assert matched_vote["kind"] == "vote"
        assert matched_vote["value"] == "down"
        assert matched_vote["paper_title"] == "Visible Feedback Paper"
        assert matched_vote["paper_match_id"] == "match-1"
        assert matched_vote["filter_name"] == "Relevant Filter"

        unmatched_vote = next(item for item in items if item["id"] == "feedback-2")
        assert unmatched_vote["kind"] == "vote"
        assert unmatched_vote["value"] == "up"
        assert unmatched_vote["paper_match_id"] is None
        assert unmatched_vote["filter_name"] is None

        note = next(item for item in items if item["id"] == "note-1")
        assert note["kind"] == "note"
        assert note["text"] == "This should inform the filter."
        assert note["value"] is None


class TestSearchRuns:
    @pytest.fixture(autouse=True)
    def _mock_queue(self, monkeypatch):
        monkeypatch.setattr("app.jobs.queues.get_queue", lambda _name: NoopQueue())

    def _setup_filters(self, client):
        client.post(
            "/onboarding/complete",
            json={
                "filters": [
                    {
                        "name": "Test",
                        "definition": {
                            "name": "Test",
                            "description": "Test",
                            "mode": "claim",
                        },
                    }
                ]
            },
        )

    def test_daily_run_lifecycle(self, client):
        self._setup_filters(client)
        resp = client.post("/search-runs/daily")
        assert resp.status_code == 200
        data = resp.json()
        job_id = data["job_id"]

        job_resp = client.get(f"/jobs/{job_id}")
        assert job_resp.status_code == 200
        job = job_resp.json()
        assert job["status"] == "queued"
        assert job["progress"] == {}

        resp = client.get("/search-runs/latest")
        assert resp.status_code == 200
        run_payload = resp.json()
        assert run_payload["run_date"] is not None
        assert run_payload["candidate_count"] is None

        run_id = run_payload["id"]
        resp = client.get("/search-runs")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

        resp = client.get("/search-runs/latest")
        assert resp.status_code == 200

        resp = client.get(f"/search-runs/{run_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == run_id

        resp = client.get(f"/search-runs/{run_id}/matches")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_get_summary_not_found_until_generated(self, client):
        self._setup_filters(client)
        create_resp = client.post("/search-runs/daily")
        assert create_resp.status_code == 200
        run_id = client.get("/search-runs/latest").json()["id"]

        resp = client.get(f"/search-runs/{run_id}/summary")
        assert resp.status_code == 404

        run_resp = client.get(f"/search-runs/{run_id}")
        assert "summary" not in run_resp.json()

    def test_summary_requires_completed_search(self, client):
        self._setup_filters(client)
        create_resp = client.post("/search-runs/daily")
        assert create_resp.status_code == 200
        run_id = client.get("/search-runs/latest").json()["id"]

        summary_resp = client.post(f"/search-runs/{run_id}/summary")
        assert summary_resp.status_code == 400
        assert "complete" in summary_resp.json()["detail"].lower()

    def test_create_daily_run_fails_fast_when_queue_unavailable(
        self, client, monkeypatch
    ):
        self._setup_filters(client)

        def broken_queue():
            raise RuntimeError("redis unavailable")

        monkeypatch.setattr("app.jobs.queues.get_queue", broken_queue)
        resp = client.post("/search-runs/daily")
        assert resp.status_code == 503

        latest = client.get("/search-runs/latest").json()
        assert latest["status"] == "failed"
        assert "redis unavailable" in (latest.get("error") or "")


class TestPapers:
    def test_paper_and_idea_map_error_paths(self, client, db_session, monkeypatch):
        resp = client.get("/papers/nonexistent-id")
        assert resp.status_code == 404

        resp = client.get("/papers/nonexistent-id/idea-map")
        assert resp.status_code == 404

        resp = client.post("/papers/nonexistent/idea-map")
        assert resp.status_code == 404

        from paper_search_core.models.paper import SQLAPaper

        paper = SQLAPaper(
            id="paper-1",
            source_type="arxiv",
            source_id="2605.00001",
            title="Test Paper",
            search_text="Test abstract.",
            authors=["Author"],
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(paper)
        db_session.commit()

        def broken_queue():
            raise RuntimeError("redis unavailable")

        monkeypatch.setattr("app.jobs.queues.get_queue", broken_queue)
        resp = client.post("/papers/paper-1/idea-map")
        assert resp.status_code == 503

        idea_map = client.get("/papers/paper-1/idea-map").json()
        assert idea_map["status"] == "failed"
        assert "redis unavailable" in idea_map["error"]
