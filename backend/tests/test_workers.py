"""Worker job tests against temporary SQLite database."""

import asyncio
import uuid
from datetime import datetime, timezone

import pytest

from app.models.filter import SQLAFilter
from app.models.onboarding_extraction import SQLAOnboardingExtraction
from paper_search_core.models.paper import SQLAPaper
from app.models.paper_match import SQLAPaperMatch
from app.models.search_run import SQLASearchRun
from app.llm.config import (
    FILTER_GENERATION_PROFILE,
    JUDGE_PROFILE,
    SUMMARY_PROFILE,
)
from app.llm.schemas import (
    ClaimFilterSearchResponse,
    FilterSearchResponse,
    OnboardingFiltersResponse,
    SearchSummaryResponse,
    TopicFilterSearchResponse,
)


class TestExtractOnboardingFilters:
    def test_persists_proposed_filters(
        self, db_session, patch_worker_database, monkeypatch
    ):
        # Create extraction record
        ext_id = str(uuid.uuid4())
        extraction = SQLAOnboardingExtraction(
            id=ext_id,
            input_text="I study mechanistic interpretability of neural networks",
            status="queued",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(extraction)
        db_session.commit()

        def fake_stream_structured_response(**kwargs):
            assert kwargs["profile"] == FILTER_GENERATION_PROFILE
            assert kwargs["response_model"] is OnboardingFiltersResponse
            kwargs["on_text_delta"](
                '{"proposedFilters":[{"id":"filter-1","name":"Mechanistic Interpretability",'
                '"description":"Mechanistic interpretability of neural networks","mode":"topic"}'
            )
            return {
                "content": {
                    "proposedFilters": [
                        {
                            "id": "filter-1",
                            "name": "Mechanistic Interpretability",
                            "description": "Mechanistic interpretability of neural networks",
                            "mode": "topic",
                        }
                    ]
                },
                "model": "test-model",
                "response_id": "onboarding-response",
            }

        monkeypatch.setattr(
            "app.jobs.onboarding.stream_structured_response",
            fake_stream_structured_response,
        )

        from app.jobs.onboarding import extract_onboarding_filters

        extract_onboarding_filters(ext_id)

        db_session.expire_all()
        updated = (
            db_session.query(SQLAOnboardingExtraction)
            .filter(SQLAOnboardingExtraction.id == ext_id)
            .first()
        )
        assert updated.status == "completed"
        assert updated.proposed_filters is not None
        assert len(updated.proposed_filters) > 0


def _paper_fixture(
    source_id: str, title: str, *, search_text: str | None = None
) -> dict:
    return {
        "source_id": source_id,
        "title": title,
        "search_text": search_text
        or f"Neural network scaling laws. Abstract for {title}.",
        "authors": ["Test Author"],
        "published_at": datetime.now(timezone.utc),
        "html_url": f"https://arxiv.org/html/{source_id}",
        "source_url": f"https://arxiv.org/abs/{source_id}",
    }


def _mock_papers_for_sources(monkeypatch, papers: list) -> None:
    monkeypatch.setattr(
        "app.jobs.daily_search.papers_for_sources",
        lambda db, sources, rd, seeded=papers: seeded,
    )


def _papers_from_dicts(db_session, papers: list[dict]) -> list:
    from app.services.papers_fts import index_paper
    from paper_search_core.models.paper import SQLAPaper

    rows: list[SQLAPaper] = []
    for p in papers:
        paper = SQLAPaper(
            id=str(uuid.uuid4()),
            source_type=p.get("source_type", "arxiv"),
            source_id=p["source_id"],
            title=p["title"],
            search_text=p.get("search_text") or "",
            authors=list(p.get("authors") or []),
            published_at=p.get("published_at"),
            html_url=p.get("html_url"),
            source_url=p.get("source_url"),
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(paper)
        db_session.flush()
        index_paper(db_session, paper)
        rows.append(paper)
    db_session.commit()
    return rows


def _daily_job(db_session, run_id: str):
    from app.models.job import SQLAJob

    return (
        db_session.query(SQLAJob)
        .filter(SQLAJob.kind == "daily_search", SQLAJob.subject_id == run_id)
        .first()
    )


def _daily_summary_job(db_session, run_id: str):
    from app.models.job import SQLAJob

    return (
        db_session.query(SQLAJob)
        .filter(SQLAJob.kind == "daily_search_summary", SQLAJob.subject_id == run_id)
        .first()
    )


def _run_summary_for_run(db_session, run_id: str) -> None:
    from app.services.jobs import create_job
    from app.jobs.daily_search_summary import summarize_daily_search

    summary_job = create_job(
        db_session,
        kind="daily_search_summary",
        subject_type="search_run",
        subject_id=run_id,
        status="queued",
    )
    db_session.commit()
    summarize_daily_search(run_id, summary_job.id)


def _create_daily_search_job(db_session, run_id: str):
    from app.services.jobs import create_job

    job = create_job(
        db_session,
        kind="daily_search",
        subject_type="search_run",
        subject_id=run_id,
        status="queued",
    )
    db_session.commit()
    return job


def _run_daily_search(db_session, run_id: str, job_id: str) -> None:
    from app.jobs.daily_search import run_daily_search

    run_daily_search(run_id, job_id)


def _extract_prompt_arxiv_id(user_prompt: str) -> str:
    for line in user_prompt.splitlines():
        if line.strip().startswith("Source ID:"):
            return line.split("Source ID:", 1)[1].strip()
    raise ValueError("Source ID not found in prompt")


def _fake_daily_async_llm(
    *, matched_arxiv_ids: set[str], assert_prompt=None, fail_arxiv_ids=None
):
    fail_arxiv_ids = fail_arxiv_ids or set()

    async def fake_async_call_llm(**kwargs):
        assert kwargs["profile"] == JUDGE_PROFILE
        assert kwargs["response_model"] in (
            ClaimFilterSearchResponse,
            TopicFilterSearchResponse,
        )
        if assert_prompt:
            assert_prompt(kwargs["user_prompt"])
        arxiv_id = _extract_prompt_arxiv_id(kwargs["user_prompt"])
        item_id = f"arxiv:{arxiv_id}"
        if arxiv_id in fail_arxiv_ids:
            raise RuntimeError(f"transient failure for {arxiv_id}")
        is_match = arxiv_id in matched_arxiv_ids
        match_data = {
            "itemId": item_id,
            "sourceType": "arxiv",
            "sourceId": arxiv_id,
        }
        if is_match:
            match_data["verdict"] = "positive"
            match_data["reason"] = "The paper directly addresses the filter."
        return {
            "content": {"matches": [match_data] if is_match else []},
            "model": "test-model",
            "response_id": f"match-response-{arxiv_id}",
        }

    return fake_async_call_llm


def _fake_summary_llm(*, matched_arxiv_id: str):
    calls = {"count": 0}
    item_id = f"arxiv:{matched_arxiv_id}"

    async def fake_async_call_llm(**kwargs):
        assert kwargs["profile"] == SUMMARY_PROFILE
        assert kwargs["response_model"] is SearchSummaryResponse
        assert '<cite itemId="' in kwargs["system_prompt"]
        calls["count"] += 1
        return {
            "content": {
                "summary": (
                    "One relevant paper matched today's filters "
                    f'<cite itemId="{item_id}"/>.'
                ),
                "citations": [
                    {
                        "paperMatchId": "",
                        "itemId": item_id,
                        "sourceType": "arxiv",
                        "sourceId": matched_arxiv_id,
                        "citedFor": "Relevant claim",
                    }
                ],
            },
            "model": "test-model",
            "response_id": "summary-response",
        }

    return fake_async_call_llm


class TestDailySearchTimeouts:
    @pytest.mark.asyncio
    async def test_pair_timeout_does_not_include_semaphore_wait(self, monkeypatch):
        from app.jobs import daily_search
        from app.models.filter import FilterPayload
        from paper_search_core.schemas.daily_search import PaperPayload

        semaphore = asyncio.Semaphore(1)
        await semaphore.acquire()
        calls = {"count": 0}

        async def fake_async_call_llm(**kwargs):
            calls["count"] += 1
            return {
                "content": {"matches": []},
                "model": "test-model",
                "response_id": "test-response",
            }

        monkeypatch.setattr(daily_search, "PAIR_TIMEOUT_SECONDS", 0.01)
        monkeypatch.setattr(daily_search, "async_call_llm", fake_async_call_llm)

        task = asyncio.create_task(
            daily_search._evaluate_filter_paper_with_timeout(
                semaphore=semaphore,
                filter=FilterPayload(
                    id="filter-1",
                    name="Test Filter",
                    definition={"name": "Test Filter", "mode": "topic"},
                ),
                paper=PaperPayload(
                    id="paper-1",
                    title="Queued Paper",
                    source_type="arxiv",
                    source_id="2605.00001",
                    item_id="arxiv:2605.00001",
                    text="Queued paper abstract.",
                    authors=["Test Author"],
                ),
            )
        )

        await asyncio.sleep(0.03)

        assert not task.done()
        assert calls["count"] == 0

        semaphore.release()
        evaluation = await asyncio.wait_for(task, timeout=1)

        assert evaluation.error is None
        assert calls["count"] == 1


class TestRunDailySearch:
    def test_persists_matches_without_inline_summary(
        self, db_session, patch_worker_database, monkeypatch
    ):

        # Create active filter
        filt = SQLAFilter(
            id=str(uuid.uuid4()),
            name="Test Filter",
            definition={
                "name": "Test Filter",
                "description": "Neural network scaling laws",
                "mode": "claim",
            },
            status="active",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(filt)

        # Create search run
        run_id = str(uuid.uuid4())
        run = SQLASearchRun(
            id=run_id,
            status="queued",
            run_date=datetime.now(timezone.utc).date(),
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(run)

        daily_papers = [
            _paper_fixture("2605.00001", "Included Scaling SQLAPaper"),
            _paper_fixture("2605.00002", "Another Current SQLAPaper"),
        ]
        db_session.commit()

        _mock_papers_for_sources(
            monkeypatch, _papers_from_dicts(db_session, daily_papers)
        )
        monkeypatch.setattr(
            "app.jobs.daily_search.async_call_llm",
            _fake_daily_async_llm(matched_arxiv_ids={"2605.00001"}),
        )
        monkeypatch.setattr(
            "app.jobs.daily_search_summary.async_call_llm",
            _fake_summary_llm(matched_arxiv_id="2605.00001"),
        )

        job = _create_daily_search_job(db_session, run_id)
        _run_daily_search(db_session, run_id, job.id)

        db_session.expire_all()
        updated_run = (
            db_session.query(SQLASearchRun).filter(SQLASearchRun.id == run_id).first()
        )
        job = _daily_job(db_session, run_id)
        assert job is not None
        assert job.status == "completed"
        assert updated_run.status == "running"
        assert updated_run.summary is None
        assert updated_run.match_count == 1
        assert updated_run.candidate_count == len(daily_papers)
        assert job.progress["total"] == len(daily_papers)
        assert job.progress["current"] == len(daily_papers)
        match_count = (
            db_session.query(SQLAPaperMatch)
            .filter(SQLAPaperMatch.search_run_id == run_id)
            .count()
        )
        assert match_count == updated_run.match_count

        _run_summary_for_run(db_session, run_id)
        db_session.expire_all()
        updated_run = (
            db_session.query(SQLASearchRun).filter(SQLASearchRun.id == run_id).first()
        )
        summary_job = _daily_summary_job(db_session, run_id)
        assert summary_job is not None
        assert summary_job.status == "completed"
        assert updated_run.status == "completed"
        assert updated_run.summary is not None

    def test_ignores_archived_filters(
        self, db_session, patch_worker_database, monkeypatch
    ):

        # Create archived filter only
        filt = SQLAFilter(
            id=str(uuid.uuid4()),
            name="Archived SQLAFilter",
            definition={
                "name": "Archived",
                "description": "Test",
                "mode": "claim",
            },
            status="archived",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            archived_at=datetime.now(timezone.utc),
        )
        db_session.add(filt)

        run_id = str(uuid.uuid4())
        run = SQLASearchRun(
            id=run_id,
            status="queued",
            run_date=datetime.now(timezone.utc).date(),
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(run)
        db_session.commit()

        _mock_papers_for_sources(
            monkeypatch,
            _papers_from_dicts(
                db_session, [_paper_fixture("2605.00004", "Fetched SQLAPaper")]
            ),
        )

        job = _create_daily_search_job(db_session, run_id)
        _run_daily_search(db_session, run_id, job.id)

        db_session.expire_all()
        updated_run = (
            db_session.query(SQLASearchRun).filter(SQLASearchRun.id == run_id).first()
        )
        job = _daily_job(db_session, run_id)
        assert job is not None
        assert job.status == "completed"
        assert updated_run.status == "running"
        assert updated_run.summary is None
        assert updated_run.match_count == 0

        _run_summary_for_run(db_session, run_id)
        db_session.expire_all()
        updated_run = (
            db_session.query(SQLASearchRun).filter(SQLASearchRun.id == run_id).first()
        )
        assert updated_run.status == "completed"
        assert updated_run.summary == "No active filters to search."

    def test_searches_only_papers_for_run_date(
        self, db_session, patch_worker_database, monkeypatch
    ):

        filt = SQLAFilter(
            id=str(uuid.uuid4()),
            name="Test Filter",
            definition={
                "name": "Test Filter",
                "description": "Neural network scaling laws",
                "mode": "claim",
            },
            status="active",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(filt)

        run_id = str(uuid.uuid4())
        run = SQLASearchRun(
            id=run_id,
            status="queued",
            run_date=datetime.now(timezone.utc).date(),
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(run)

        excluded = SQLAPaper(
            id=str(uuid.uuid4()),
            source_type="arxiv",
            source_id="2401.00002",
            title="Excluded SQLAPaper",
            search_text="A cached paper from another run.",
            authors=["Author"],
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(excluded)
        db_session.commit()

        _mock_papers_for_sources(
            monkeypatch,
            _papers_from_dicts(
                db_session, [_paper_fixture("2401.00001", "Included SQLAPaper")]
            ),
        )

        def assert_prompt(user_prompt: str):
            assert "Included SQLAPaper" in user_prompt
            assert "Excluded SQLAPaper" not in user_prompt

        monkeypatch.setattr(
            "app.jobs.daily_search.async_call_llm",
            _fake_daily_async_llm(
                matched_arxiv_ids={"2401.00001"},
                assert_prompt=assert_prompt,
            ),
        )
        job = _create_daily_search_job(db_session, run_id)
        _run_daily_search(db_session, run_id, job.id)

        db_session.expire_all()
        updated_run = (
            db_session.query(SQLASearchRun).filter(SQLASearchRun.id == run_id).first()
        )
        matches = db_session.query(SQLAPaperMatch).all()
        included = (
            db_session.query(SQLAPaper)
            .filter(
                SQLAPaper.source_type == "arxiv", SQLAPaper.source_id == "2401.00001"
            )
            .first()
        )

        assert updated_run.candidate_count == 1
        assert {m.paper_id for m in matches} == {included.id}

    def test_missing_openrouter_key_fails_without_demo_data(
        self, db_session, patch_worker_database, monkeypatch
    ):

        filt = SQLAFilter(
            id=str(uuid.uuid4()),
            name="Test Filter",
            definition={
                "name": "Test Filter",
                "description": "Neural network scaling laws",
                "mode": "claim",
            },
            status="active",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(filt)

        run_id = str(uuid.uuid4())
        run = SQLASearchRun(
            id=run_id,
            status="queued",
            run_date=datetime.now(timezone.utc).date(),
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(run)

        from app.services.papers_fts import index_paper

        paper = SQLAPaper(
            id=str(uuid.uuid4()),
            source_type="arxiv",
            source_id="2605.00003",
            title="Current SQLAPaper",
            search_text="Neural network scaling laws in large language models.",
            authors=["Author"],
            published_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(paper)
        db_session.flush()
        index_paper(db_session, paper)
        db_session.commit()

        _mock_papers_for_sources(monkeypatch, [paper])
        monkeypatch.setattr("app.config.settings.OPENROUTER_API_KEY", "")

        job = _create_daily_search_job(db_session, run_id)

        try:
            _run_daily_search(db_session, run_id, job.id)
        except RuntimeError as exc:
            assert "OPENROUTER_API_KEY" in str(exc)
        else:
            raise AssertionError("Expected missing OPENROUTER_API_KEY to fail")

        db_session.expire_all()
        updated_run = (
            db_session.query(SQLASearchRun).filter(SQLASearchRun.id == run_id).first()
        )
        matches = db_session.query(SQLAPaperMatch).all()
        assert updated_run.status == "failed"
        assert "OPENROUTER_API_KEY" in updated_run.error
        assert matches == []

    def test_pair_failures_increment_progress_when_some_pairs_succeed(
        self, db_session, patch_worker_database, monkeypatch
    ):

        filt = SQLAFilter(
            id=str(uuid.uuid4()),
            name="Test Filter",
            definition={
                "name": "Test Filter",
                "description": "Neural network scaling laws",
                "mode": "claim",
            },
            status="active",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(filt)

        run_id = str(uuid.uuid4())
        db_session.add(
            SQLASearchRun(
                id=run_id,
                status="queued",
                run_date=datetime.now(timezone.utc).date(),
                created_at=datetime.now(timezone.utc),
            )
        )
        daily_papers = [
            _paper_fixture("2605.00010", "Successful SQLAPaper"),
            _paper_fixture("2605.00011", "Failing SQLAPaper"),
        ]
        db_session.commit()

        _mock_papers_for_sources(
            monkeypatch, _papers_from_dicts(db_session, daily_papers)
        )
        monkeypatch.setattr(
            "app.jobs.daily_search.async_call_llm",
            _fake_daily_async_llm(
                matched_arxiv_ids={"2605.00010"},
                fail_arxiv_ids={"2605.00011"},
            ),
        )
        monkeypatch.setattr(
            "app.jobs.daily_search_summary.async_call_llm",
            _fake_summary_llm(matched_arxiv_id="2605.00010"),
        )

        job = _create_daily_search_job(db_session, run_id)
        _run_daily_search(db_session, run_id, job.id)

        db_session.expire_all()
        updated_run = (
            db_session.query(SQLASearchRun).filter(SQLASearchRun.id == run_id).first()
        )
        job = _daily_job(db_session, run_id)
        assert job is not None
        assert job.status == "completed"
        assert updated_run.status == "running"
        assert updated_run.summary is None
        assert job.progress["total"] == 2
        assert job.progress["current"] == 2
        assert updated_run.match_count == 1
        match_count = (
            db_session.query(SQLAPaperMatch)
            .filter(SQLAPaperMatch.search_run_id == run_id)
            .count()
        )
        assert match_count == 1

        _run_summary_for_run(db_session, run_id)
        db_session.expire_all()
        updated_run = (
            db_session.query(SQLASearchRun).filter(SQLASearchRun.id == run_id).first()
        )
        assert updated_run.status == "completed"
        assert updated_run.summary is not None

    def test_all_pair_failures_mark_run_failed(
        self, db_session, patch_worker_database, monkeypatch
    ):

        filt = SQLAFilter(
            id=str(uuid.uuid4()),
            name="Test Filter",
            definition={
                "name": "Test Filter",
                "description": "Neural network scaling laws",
                "mode": "claim",
            },
            status="active",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(filt)

        run_id = str(uuid.uuid4())
        db_session.add(
            SQLASearchRun(
                id=run_id,
                status="queued",
                run_date=datetime.now(timezone.utc).date(),
                created_at=datetime.now(timezone.utc),
            )
        )
        daily_papers = [_paper_fixture("2605.00012", "Failing SQLAPaper")]
        db_session.commit()

        _mock_papers_for_sources(
            monkeypatch, _papers_from_dicts(db_session, daily_papers)
        )
        (
            monkeypatch.setattr(
                "app.jobs.daily_search.async_call_llm",
                _fake_daily_async_llm(
                    matched_arxiv_ids=set(),
                    fail_arxiv_ids={"2605.00012"},
                ),
            ),
        )

        job = _create_daily_search_job(db_session, run_id)

        try:
            _run_daily_search(db_session, run_id, job.id)
        except RuntimeError as exc:
            assert "All 1 filter-item evaluations failed" in str(exc)
        else:
            raise AssertionError("Expected all pair failures to fail the run")

        db_session.expire_all()
        updated_run = (
            db_session.query(SQLASearchRun).filter(SQLASearchRun.id == run_id).first()
        )
        job = _daily_job(db_session, run_id)
        assert job is not None
        assert updated_run.status == "failed"
        assert job.progress["total"] == 1
        assert job.progress["current"] == 1

    def test_progress_total_equals_selected_pairs(
        self, db_session, patch_worker_database, monkeypatch
    ):
        scaling_filter = SQLAFilter(
            id=str(uuid.uuid4()),
            name="Scaling Filter",
            definition={
                "description": "neural network scaling laws",
                "mode": "claim",
            },
            status="active",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        quantum_filter = SQLAFilter(
            id=str(uuid.uuid4()),
            name="Quantum Filter",
            definition={
                "description": "quantum entanglement physics",
                "mode": "claim",
            },
            status="active",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(scaling_filter)
        db_session.add(quantum_filter)

        run_id = str(uuid.uuid4())
        db_session.add(
            SQLASearchRun(
                id=run_id,
                status="queued",
                run_date=datetime.now(timezone.utc).date(),
                created_at=datetime.now(timezone.utc),
            )
        )
        daily_papers = [
            _paper_fixture(
                "2605.00100",
                "Scaling paper",
                search_text="neural network scaling laws in transformers",
            ),
            _paper_fixture(
                "2605.00101",
                "Quantum paper",
                search_text="quantum entanglement and bell tests",
            ),
            _paper_fixture(
                "2605.00102",
                "Unrelated paper",
                search_text="classical thermodynamics of gases",
            ),
        ]
        db_session.commit()

        _mock_papers_for_sources(
            monkeypatch, _papers_from_dicts(db_session, daily_papers)
        )
        llm_calls = {"count": 0}

        async def counting_llm(**kwargs):
            llm_calls["count"] += 1
            return {
                "content": {"matches": []},
                "model": "test-model",
                "response_id": "test",
            }

        monkeypatch.setattr("app.jobs.daily_search.async_call_llm", counting_llm)

        job = _create_daily_search_job(db_session, run_id)
        _run_daily_search(db_session, run_id, job.id)

        db_session.expire_all()
        job = _daily_job(db_session, run_id)
        assert job is not None
        assert job.progress["total"] == llm_calls["count"]
        assert job.progress["total"] == job.progress["current"]
        assert llm_calls["count"] >= 2
        assert llm_calls["count"] < len(daily_papers) * 2

    def test_no_fts_candidates_completes_with_zero_matches(
        self, db_session, patch_worker_database, monkeypatch
    ):
        filt = SQLAFilter(
            id=str(uuid.uuid4()),
            name="Astrobiology Filter",
            definition={
                "description": "exoplanet biosignatures spectroscopy",
                "mode": "claim",
            },
            status="active",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(filt)

        run_id = str(uuid.uuid4())
        db_session.add(
            SQLASearchRun(
                id=run_id,
                status="queued",
                run_date=datetime.now(timezone.utc).date(),
                created_at=datetime.now(timezone.utc),
            )
        )
        daily_papers = [
            _paper_fixture(
                "2605.00200",
                "Scaling paper",
                search_text="neural network scaling laws only",
            ),
        ]
        db_session.commit()

        _mock_papers_for_sources(
            monkeypatch, _papers_from_dicts(db_session, daily_papers)
        )
        llm_calls = {"count": 0}

        async def counting_llm(**kwargs):
            llm_calls["count"] += 1
            return {
                "content": {"matches": []},
                "model": "test-model",
                "response_id": "test",
            }

        monkeypatch.setattr("app.jobs.daily_search.async_call_llm", counting_llm)

        job = _create_daily_search_job(db_session, run_id)
        _run_daily_search(db_session, run_id, job.id)

        db_session.expire_all()
        updated_run = (
            db_session.query(SQLASearchRun).filter(SQLASearchRun.id == run_id).first()
        )
        job = _daily_job(db_session, run_id)
        assert job is not None
        assert job.status == "completed"
        assert updated_run.match_count == 0
        assert job.progress == {"current": 0, "total": 0}
        assert llm_calls["count"] == 0


class TestSummarizeDailySearch:
    def test_summarize_reads_matches_from_database(
        self, db_session, patch_worker_database, monkeypatch
    ):

        filt_id = str(uuid.uuid4())
        filt = SQLAFilter(
            id=filt_id,
            name="Test Filter",
            definition={
                "name": "Test Filter",
                "description": "Neural network scaling laws",
                "mode": "claim",
            },
            status="active",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(filt)

        run_id = str(uuid.uuid4())
        run = SQLASearchRun(
            id=run_id,
            status="running",
            run_date=datetime.now(timezone.utc).date(),
            candidate_count=1,
            candidate_counts={"arxiv": 1},
            match_count=1,
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(run)

        paper = SQLAPaper(
            id=str(uuid.uuid4()),
            source_type="arxiv",
            source_id="2605.00001",
            title="Included Scaling SQLAPaper",
            search_text="Abstract",
            authors=["Author"],
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(paper)
        db_session.flush()
        db_session.add(
            SQLAPaperMatch(
                search_run_id=run_id,
                filter_id=filt_id,
                paper_id=paper.id,
                result="The paper directly addresses the filter.",
                llm_model="test-model",
                llm_response_id="match-response",
            )
        )
        db_session.commit()

        monkeypatch.setattr(
            "app.jobs.daily_search_summary.async_call_llm",
            _fake_summary_llm(matched_arxiv_id="2605.00001"),
        )

        from app.jobs.daily_search_summary import summarize_daily_search

        summarize_daily_search(run_id)

        db_session.expire_all()
        updated_run = (
            db_session.query(SQLASearchRun).filter(SQLASearchRun.id == run_id).first()
        )
        summary_job = _daily_summary_job(db_session, run_id)
        assert summary_job is not None
        assert summary_job.status == "completed"
        assert updated_run.status == "completed"
        assert updated_run.summary is not None
        assert "One relevant paper matched today's filters" in updated_run.summary
