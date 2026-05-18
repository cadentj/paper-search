"""Backend API integration tests."""

from datetime import datetime, timezone

import pytest


class NoopQueue:
    def enqueue(self, *args, **kwargs):
        return None


class TestOnboarding:
    @pytest.fixture(autouse=True)
    def _mock_queue(self, monkeypatch):
        monkeypatch.setattr("app.api.onboarding.get_queue", lambda: NoopQueue())

    def test_fresh_db_reports_incomplete(self, client):
        resp = client.get("/onboarding/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["completed"] is False
        assert data["active_filter_count"] == 0

    def test_create_extraction(self, client):
        resp = client.post(
            "/onboarding/extractions",
            json={"input_text": "I study mechanistic interpretability"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("queued", "running", "completed")
        assert data["input_text"] == "I study mechanistic interpretability"

    def test_get_extraction(self, client):
        resp = client.post(
            "/onboarding/extractions",
            json={"input_text": "AI safety research"},
        )
        ext_id = resp.json()["id"]
        resp2 = client.get(f"/onboarding/extractions/{ext_id}")
        assert resp2.status_code == 200
        assert resp2.json()["id"] == ext_id

    def test_get_nonexistent_extraction(self, client):
        resp = client.get("/onboarding/extractions/nonexistent-id")
        assert resp.status_code == 404

    def test_complete_onboarding_creates_filters(self, client):
        filters_payload = [
            {
                "name": "Test Filter",
                "definition": {
                    "name": "Test Filter",
                    "description": "Test statement",
                    "mode": "warrants",
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

    def test_create_extraction_fails_fast_when_queue_unavailable(self, client, monkeypatch):
        def broken_queue():
            raise RuntimeError("redis unavailable")

        monkeypatch.setattr("app.api.onboarding.get_queue", broken_queue)
        resp = client.post(
            "/onboarding/extractions",
            json={"input_text": "I study mechanistic interpretability"},
        )
        assert resp.status_code == 503
        assert "Could not enqueue onboarding extraction" in resp.text


class TestFilters:
    def _create_filter(self, client, name="My Filter"):
        return client.post(
            "/filters",
            json={
                "name": name,
                "definition": {
                    "name": name,
                    "description": "Test",
                    "mode": "warrants",
                },
            },
        )

    def test_create_filter(self, client):
        resp = self._create_filter(client)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "My Filter"
        assert data["status"] == "active"

    def test_list_filters(self, client):
        self._create_filter(client, "Filter A")
        self._create_filter(client, "Filter B")
        resp = client.get("/filters")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_update_filter(self, client):
        create_resp = self._create_filter(client)
        fid = create_resp.json()["id"]
        resp = client.patch(
            f"/filters/{fid}",
            json={"name": "Updated Name"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"

    def test_archive_filter(self, client):
        create_resp = self._create_filter(client)
        fid = create_resp.json()["id"]
        resp = client.post(f"/filters/{fid}/archive")
        assert resp.status_code == 200
        assert resp.json()["status"] == "archived"
        assert resp.json()["archived_at"] is not None

    def test_restore_filter(self, client):
        create_resp = self._create_filter(client)
        fid = create_resp.json()["id"]
        client.post(f"/filters/{fid}/archive")
        resp = client.post(f"/filters/{fid}/restore")
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"
        assert resp.json()["archived_at"] is None

    def test_archive_nonexistent(self, client):
        resp = client.post("/filters/nonexistent/archive")
        assert resp.status_code == 404


class TestSearchRuns:
    @pytest.fixture(autouse=True)
    def _mock_queue(self, monkeypatch):
        monkeypatch.setattr("app.api.search.get_queue", lambda: NoopQueue())

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
                            "mode": "warrants",
                        },
                    }
                ]
            },
        )

    def test_create_daily_run(self, client):
        self._setup_filters(client)
        resp = client.post("/search-runs/daily")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "queued"
        assert data["stage"] == "queued"
        assert data["progress_current"] == 0
        assert data["progress_total"] == 1
        assert "worker" in data["progress_message"]
        assert data["run_date"] is not None
        assert data["candidate_count"] is None

    def test_create_daily_run_fails_fast_when_queue_unavailable(self, client, monkeypatch):
        self._setup_filters(client)

        def broken_queue():
            raise RuntimeError("redis unavailable")

        monkeypatch.setattr("app.api.search.get_queue", broken_queue)
        resp = client.post("/search-runs/daily")
        assert resp.status_code == 503

        latest = client.get("/search-runs/latest").json()
        assert latest["status"] == "failed"
        assert latest["stage"] == "failed"
        assert "Could not enqueue daily search" in latest["error"]

    def test_list_search_runs(self, client):
        self._setup_filters(client)
        client.post("/search-runs/daily")
        resp = client.get("/search-runs")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_get_latest_search_run(self, client):
        self._setup_filters(client)
        client.post("/search-runs/daily")
        resp = client.get("/search-runs/latest")
        assert resp.status_code == 200

    def test_get_search_run(self, client):
        self._setup_filters(client)
        create_resp = client.post("/search-runs/daily")
        run_id = create_resp.json()["id"]
        resp = client.get(f"/search-runs/{run_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == run_id

    def test_get_matches(self, client):
        self._setup_filters(client)
        create_resp = client.post("/search-runs/daily")
        run_id = create_resp.json()["id"]
        resp = client.get(f"/search-runs/{run_id}/matches")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestPapers:
    def _create_paper(self, client):
        """Create a paper by running a daily search to upsert mock papers."""
        client.post(
            "/onboarding/complete",
            json={
                "filters": [
                    {
                        "name": "Test",
                        "definition": {
                            "name": "Test",
                            "description": "Test",
                            "mode": "warrants",
                        },
                    }
                ]
            },
        )
        client.post("/search-runs/daily")
        # Get papers from search run matches or list
        return None

    def test_get_nonexistent_paper(self, client):
        resp = client.get("/papers/nonexistent-id")
        assert resp.status_code == 404

    def test_get_nonexistent_idea_map(self, client):
        resp = client.get("/papers/nonexistent-id/idea-map")
        assert resp.status_code == 404

    def test_create_idea_map_fails_fast_when_queue_unavailable(
        self, client, db_session, monkeypatch
    ):
        from app.models.paper import Paper

        paper = Paper(
            id="paper-1",
            arxiv_id="2605.00001",
            title="Test Paper",
            abstract="Test abstract.",
            authors=["Author"],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(paper)
        db_session.commit()

        def broken_queue():
            raise RuntimeError("redis unavailable")

        monkeypatch.setattr("app.api.papers.get_queue", broken_queue)
        resp = client.post("/papers/paper-1/idea-map")
        assert resp.status_code == 503

        idea_map = client.get("/papers/paper-1/idea-map").json()
        assert idea_map["status"] == "failed"
        assert "Could not enqueue idea map" in idea_map["error"]


class TestDevReset:
    def test_reset_clears_state(self, client):
        # Create some data
        client.post(
            "/onboarding/complete",
            json={
                "filters": [
                    {
                        "name": "Test",
                        "definition": {
                            "name": "Test",
                            "description": "Test",
                            "mode": "warrants",
                        },
                    }
                ]
            },
        )
        # Verify data exists
        assert client.get("/onboarding/status").json()["completed"] is True

        # Reset
        resp = client.post("/dev/reset-onboarding")
        assert resp.status_code == 200

        # Verify cleared
        assert client.get("/onboarding/status").json()["completed"] is False
        assert client.get("/filters").json() == []

    def test_health_endpoint(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestIdeaMapIdempotent:
    def test_post_idea_map_nonexistent_paper(self, client):
        resp = client.post("/papers/nonexistent/idea-map")
        assert resp.status_code == 404
