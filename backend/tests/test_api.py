"""Backend API integration tests."""

import uuid


class TestOnboarding:
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
                    "statement": "Test statement",
                    "search": {"instructions": "Search for tests", "outputMode": "warrants"},
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


class TestFilters:
    def _create_filter(self, client, name="My Filter"):
        return client.post(
            "/filters",
            json={
                "name": name,
                "definition": {
                    "name": name,
                    "statement": "Test",
                    "search": {"instructions": "Search", "outputMode": "warrants"},
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
    def _setup_filters(self, client):
        client.post(
            "/onboarding/complete",
            json={
                "filters": [
                    {
                        "name": "Test",
                        "definition": {
                            "name": "Test",
                            "statement": "Test",
                            "search": {"instructions": "Test", "outputMode": "warrants"},
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
        assert data["status"] in ("queued", "running", "completed")
        assert data["run_date"] is not None

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
                            "statement": "Test",
                            "search": {"instructions": "Test", "outputMode": "warrants"},
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


class TestFeedback:
    def test_submit_feedback(self, client):
        resp = client.post(
            "/feedback",
            json={
                "target_type": "paper_match",
                "target_id": str(uuid.uuid4()),
                "value": "upvote",
            },
        )
        assert resp.status_code == 200

    def test_not_interested_archives_filter(self, client):
        create_resp = client.post(
            "/filters",
            json={
                "name": "To Archive",
                "definition": {
                    "name": "To Archive",
                    "statement": "Test",
                    "search": {"instructions": "Test", "outputMode": "warrants"},
                },
            },
        )
        fid = create_resp.json()["id"]
        resp = client.post(
            "/feedback",
            json={
                "target_type": "filter",
                "target_id": fid,
                "value": "not_interested",
            },
        )
        assert resp.status_code == 200

        filter_resp = client.get("/filters")
        filters = filter_resp.json()
        archived = [f for f in filters if f["id"] == fid]
        assert len(archived) == 1
        assert archived[0]["status"] == "archived"


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
                            "statement": "Test",
                            "search": {"instructions": "Test", "outputMode": "warrants"},
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
