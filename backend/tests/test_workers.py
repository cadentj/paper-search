"""Worker job tests against temporary SQLite database."""

import uuid
from datetime import datetime, timezone

from app.models.filter import Filter
from app.models.onboarding_extraction import OnboardingExtraction
from app.models.paper import Paper
from app.models.paper_match import PaperMatch
from app.models.search_run import SearchRun
from app.llm.config import (
    FILTER_GENERATION_PROFILE,
    JUDGE_PROFILE,
    SUMMARY_PROFILE,
)
from app.llm.schemas import (
    FilterSearchResponse,
    OnboardingFiltersResponse,
    SearchSummaryResponse,
)


class TestExtractOnboardingFilters:
    def test_persists_proposed_filters(self, db_session, db_engine, monkeypatch):
        from sqlalchemy.orm import sessionmaker

        # Create extraction record
        ext_id = str(uuid.uuid4())
        extraction = OnboardingExtraction(
            id=ext_id,
            input_text="I study mechanistic interpretability of neural networks",
            status="queued",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(extraction)
        db_session.commit()

        # Patch SessionLocal in the jobs module to use test DB
        TestSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)

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

        monkeypatch.setattr("app.jobs.onboarding.SessionLocal", TestSession)
        monkeypatch.setattr(
            "app.jobs.onboarding.stream_structured_response",
            fake_stream_structured_response,
        )

        from app.jobs.onboarding import extract_onboarding_filters
        extract_onboarding_filters(ext_id)

        db_session.expire_all()
        updated = db_session.query(OnboardingExtraction).filter(
            OnboardingExtraction.id == ext_id
        ).first()
        assert updated.status == "completed"
        assert updated.proposed_filters is not None
        assert len(updated.proposed_filters) > 0


def _paper_fixture(arxiv_id: str, title: str) -> dict:
    return {
        "arxiv_id": arxiv_id,
        "title": title,
        "abstract": f"Abstract for {title}.",
        "authors": ["Test Author"],
        "categories": ["cs.AI"],
        "published_at": datetime.now(timezone.utc),
        "html_url": f"https://arxiv.org/html/{arxiv_id}",
        "landing_url": f"https://arxiv.org/abs/{arxiv_id}",
    }


def _source_fetch_result_from_paper_dicts(papers: list[dict]):
    from app.services.source_providers import CandidateItem, SourceFetchResult

    items = [
        CandidateItem(
            source_type="arxiv",
            source_id=p["arxiv_id"],
            title=p["title"],
            display_text=p.get("abstract") or "",
            authors=list(p.get("authors") or []),
            categories=list(p.get("categories") or []),
            published_at=p.get("published_at"),
            html_url=p.get("html_url"),
            landing_url=p.get("landing_url"),
            source_url=p.get("landing_url"),
            arxiv_id=p["arxiv_id"],
        )
        for p in papers
    ]
    return SourceFetchResult(items=items)


def _daily_job(db_session, run_id: str):
    from app.models.job import Job

    return (
        db_session.query(Job)
        .filter(Job.kind == "daily_search", Job.subject_id == run_id)
        .first()
    )


def _extract_prompt_arxiv_id(user_prompt: str) -> str:
    for line in user_prompt.splitlines():
        if line.strip().startswith("Source ID:"):
            return line.split("Source ID:", 1)[1].strip()
    raise ValueError("Source ID not found in prompt")


def _fake_daily_async_llm(*, matched_arxiv_ids: set[str], assert_prompt=None, fail_arxiv_ids=None):
    fail_arxiv_ids = fail_arxiv_ids or set()

    async def fake_async_call_llm(**kwargs):
        assert kwargs["profile"] == JUDGE_PROFILE
        assert kwargs["response_model"] is FilterSearchResponse
        if assert_prompt:
            assert_prompt(kwargs["user_prompt"])
        arxiv_id = _extract_prompt_arxiv_id(kwargs["user_prompt"])
        item_id = f"arxiv:{arxiv_id}"
        if arxiv_id in fail_arxiv_ids:
            raise RuntimeError(f"transient failure for {arxiv_id}")
        is_match = arxiv_id in matched_arxiv_ids
        return {
            "content": {
                "matches": [
                    {
                        "itemId": item_id,
                        "sourceType": "arxiv",
                        "sourceId": arxiv_id,
                        "result": (
                            "The paper directly addresses the filter."
                            if is_match
                            else ""
                        ),
                    }
                ]
            },
            "model": "test-model",
            "response_id": f"match-response-{arxiv_id}",
        }

    return fake_async_call_llm


def _fake_summary_llm(*, matched_arxiv_id: str):
    calls = {"count": 0}
    item_id = f"arxiv:{matched_arxiv_id}"

    def fake_call_llm(**kwargs):
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

    return fake_call_llm


class TestRunDailySearch:
    def test_persists_matches_and_summary(self, db_session, db_engine, monkeypatch):
        from sqlalchemy.orm import sessionmaker

        # Create active filter
        filt = Filter(
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
        run = SearchRun(
            id=run_id,
            status="queued",
            run_date=datetime.now(timezone.utc).date(),
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(run)

        daily_papers = [
            _paper_fixture("2605.00001", "Included Scaling Paper"),
            _paper_fixture("2605.00002", "Another Current Paper"),
        ]
        db_session.commit()

        # Patch SessionLocal
        TestSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
        monkeypatch.setattr("app.jobs.daily_search.SessionLocal", TestSession)
        monkeypatch.setattr(
            "app.jobs.daily_search.candidates_for_sources",
            lambda sources, rd, p=daily_papers: _source_fetch_result_from_paper_dicts(p),
        )
        monkeypatch.setattr(
            "app.jobs.daily_search.async_call_llm",
            _fake_daily_async_llm(matched_arxiv_ids={"2605.00001"}),
        )
        monkeypatch.setattr(
            "app.jobs.daily_search.call_llm",
            _fake_summary_llm(matched_arxiv_id="2605.00001"),
        )

        from app.jobs.daily_search import run_daily_search
        run_daily_search(run_id)

        db_session.expire_all()
        updated_run = db_session.query(SearchRun).filter(SearchRun.id == run_id).first()
        job = _daily_job(db_session, run_id)
        assert job is not None
        assert updated_run.status == "completed"
        assert job.progress["stage"] == "completed"
        assert updated_run.summary is not None
        assert updated_run.match_count is not None
        assert updated_run.candidate_count == len(daily_papers)
        assert job.progress["total"] == len(daily_papers)
        assert job.progress["current"] == job.progress["total"]
        assert len(job.progress.get("log", [])) >= 3

    def test_ignores_archived_filters(self, db_session, db_engine, monkeypatch):
        from sqlalchemy.orm import sessionmaker

        # Create archived filter only
        filt = Filter(
            id=str(uuid.uuid4()),
            name="Archived Filter",
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
        run = SearchRun(
            id=run_id,
            status="queued",
            run_date=datetime.now(timezone.utc).date(),
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(run)
        db_session.commit()

        TestSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
        monkeypatch.setattr("app.jobs.daily_search.SessionLocal", TestSession)
        monkeypatch.setattr(
            "app.jobs.daily_search.candidates_for_sources",
            lambda sources, rd: _source_fetch_result_from_paper_dicts(
                [_paper_fixture("2605.00004", "Fetched Paper")]
            ),
        )

        from app.jobs.daily_search import run_daily_search
        run_daily_search(run_id)

        db_session.expire_all()
        updated_run = db_session.query(SearchRun).filter(SearchRun.id == run_id).first()
        job = _daily_job(db_session, run_id)
        assert job is not None
        assert updated_run.status == "completed"
        assert job.progress["stage"] == "completed"
        assert updated_run.match_count == 0

    def test_searches_only_fetched_candidate_papers(self, db_session, db_engine, monkeypatch):
        from sqlalchemy.orm import sessionmaker

        filt = Filter(
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
        run = SearchRun(
            id=run_id,
            status="queued",
            run_date=datetime.now(timezone.utc).date(),
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(run)

        excluded = Paper(
            id=str(uuid.uuid4()),
            arxiv_id="2401.00002",
            title="Excluded Paper",
            abstract="A cached paper from another run.",
            authors=["Author"],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(excluded)
        db_session.commit()

        TestSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
        monkeypatch.setattr("app.jobs.daily_search.SessionLocal", TestSession)
        monkeypatch.setattr(
            "app.jobs.daily_search.candidates_for_sources",
            lambda sources, rd: _source_fetch_result_from_paper_dicts(
                [_paper_fixture("2401.00001", "Included Paper")]
            ),
        )

        def assert_prompt(user_prompt: str):
            assert "Included Paper" in user_prompt
            assert "Excluded Paper" not in user_prompt

        monkeypatch.setattr(
            "app.jobs.daily_search.async_call_llm",
            _fake_daily_async_llm(
                matched_arxiv_ids={"2401.00001"},
                assert_prompt=assert_prompt,
            ),
        )
        monkeypatch.setattr(
            "app.jobs.daily_search.call_llm",
            _fake_summary_llm(matched_arxiv_id="2401.00001"),
        )

        from app.jobs.daily_search import run_daily_search
        run_daily_search(run_id)

        db_session.expire_all()
        updated_run = db_session.query(SearchRun).filter(SearchRun.id == run_id).first()
        matches = db_session.query(PaperMatch).all()
        included = db_session.query(Paper).filter(Paper.arxiv_id == "2401.00001").first()

        assert updated_run.candidate_count == 1
        assert {m.paper_id for m in matches} == {included.id}

    def test_missing_openrouter_key_fails_without_demo_data(
        self, db_session, db_engine, monkeypatch
    ):
        from sqlalchemy.orm import sessionmaker

        filt = Filter(
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
        run = SearchRun(
            id=run_id,
            status="queued",
            run_date=datetime.now(timezone.utc).date(),
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(run)

        paper = Paper(
            id=str(uuid.uuid4()),
            arxiv_id="2605.00003",
            title="Current Paper",
            abstract="A current paper that requires LLM matching.",
            authors=["Author"],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(paper)
        db_session.commit()

        TestSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
        monkeypatch.setattr("app.jobs.daily_search.SessionLocal", TestSession)
        monkeypatch.setattr(
            "app.jobs.daily_search.candidates_for_sources",
            lambda sources, rd: _source_fetch_result_from_paper_dicts(
                [_paper_fixture("2605.00003", "Current Paper")]
            ),
        )
        monkeypatch.setattr("app.core.config.settings.OPENROUTER_API_KEY", "")

        from app.jobs.daily_search import run_daily_search

        try:
            run_daily_search(run_id)
        except RuntimeError as exc:
            assert "OPENROUTER_API_KEY" in str(exc)
        else:
            raise AssertionError("Expected missing OPENROUTER_API_KEY to fail")

        db_session.expire_all()
        updated_run = db_session.query(SearchRun).filter(SearchRun.id == run_id).first()
        matches = db_session.query(PaperMatch).all()
        assert updated_run.status == "failed"
        assert "OPENROUTER_API_KEY" in updated_run.error
        assert matches == []

    def test_pair_failures_increment_progress_when_some_pairs_succeed(
        self, db_session, db_engine, monkeypatch
    ):
        from sqlalchemy.orm import sessionmaker

        filt = Filter(
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
            SearchRun(
                id=run_id,
                status="queued",
                run_date=datetime.now(timezone.utc).date(),
                created_at=datetime.now(timezone.utc),
            )
        )
        daily_papers = [
            _paper_fixture("2605.00010", "Successful Paper"),
            _paper_fixture("2605.00011", "Failing Paper"),
        ]
        db_session.commit()

        TestSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
        monkeypatch.setattr("app.jobs.daily_search.SessionLocal", TestSession)
        monkeypatch.setattr(
            "app.jobs.daily_search.candidates_for_sources",
            lambda sources, rd, p=daily_papers: _source_fetch_result_from_paper_dicts(p),
        )
        monkeypatch.setattr(
            "app.jobs.daily_search.async_call_llm",
            _fake_daily_async_llm(
                matched_arxiv_ids={"2605.00010"},
                fail_arxiv_ids={"2605.00011"},
            ),
        )
        monkeypatch.setattr(
            "app.jobs.daily_search.call_llm",
            _fake_summary_llm(matched_arxiv_id="2605.00010"),
        )

        from app.jobs.daily_search import run_daily_search
        run_daily_search(run_id)

        db_session.expire_all()
        updated_run = db_session.query(SearchRun).filter(SearchRun.id == run_id).first()
        job = _daily_job(db_session, run_id)
        assert job is not None
        assert updated_run.status == "completed"
        assert job.progress["current"] == 2
        assert job.progress["total"] == 2
        assert updated_run.match_count == 1
        log_msgs = [entry.get("message", "") for entry in job.progress.get("log", [])]
        assert any("2605.00011" in m or "pair" in m.lower() for m in log_msgs)

    def test_all_pair_failures_mark_run_failed(self, db_session, db_engine, monkeypatch):
        from sqlalchemy.orm import sessionmaker

        filt = Filter(
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
            SearchRun(
                id=run_id,
                status="queued",
                run_date=datetime.now(timezone.utc).date(),
                created_at=datetime.now(timezone.utc),
            )
        )
        daily_papers = [_paper_fixture("2605.00012", "Failing Paper")]
        db_session.commit()

        TestSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
        monkeypatch.setattr("app.jobs.daily_search.SessionLocal", TestSession)
        monkeypatch.setattr(
            "app.jobs.daily_search.candidates_for_sources",
            lambda sources, rd, p=daily_papers: _source_fetch_result_from_paper_dicts(p),
        )
        monkeypatch.setattr(
            "app.jobs.daily_search.async_call_llm",
            _fake_daily_async_llm(
                matched_arxiv_ids=set(),
                fail_arxiv_ids={"2605.00012"},
            ),
        )

        from app.jobs.daily_search import run_daily_search

        try:
            run_daily_search(run_id)
        except RuntimeError as exc:
            assert "All 1 filter-item evaluations failed" in str(exc)
        else:
            raise AssertionError("Expected all pair failures to fail the run")

        db_session.expire_all()
        updated_run = db_session.query(SearchRun).filter(SearchRun.id == run_id).first()
        job = _daily_job(db_session, run_id)
        assert job is not None
        assert updated_run.status == "failed"
        assert job.progress["stage"] == "failed"
        assert job.progress["current"] == 1
        assert job.progress["total"] == 1
