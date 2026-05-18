"""Worker job tests against temporary SQLite database."""

import uuid
from datetime import datetime, timezone

from app.models.filter import Filter
from app.models.onboarding_extraction import OnboardingExtraction
from app.models.paper import Paper
from app.models.paper_match import PaperMatch
from app.models.search_run import SearchRun
from app.models.idea_map import IdeaMap
from app.models.paper_html import PaperHtml
from app.llm.config import (
    FILTER_GENERATION_PROFILE,
    IDEA_MAP_PROFILE,
    JUDGE_PROFILE,
    SUMMARY_PROFILE,
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
            kwargs["on_text_delta"](
                '{"proposedFilters":[{"id":"filter-1","name":"Mechanistic Interpretability",'
                '"description":"Mechanistic interpretability of neural networks","mode":"relevance"}'
            )
            return {
                "content": {
                    "proposedFilters": [
                        {
                            "id": "filter-1",
                            "name": "Mechanistic Interpretability",
                            "description": "Mechanistic interpretability of neural networks",
                            "mode": "relevance",
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


def _extract_prompt_arxiv_id(user_prompt: str) -> str:
    marker = "ArXiv ID: "
    start = user_prompt.index(marker) + len(marker)
    return user_prompt[start:].split("\n", 1)[0].strip()


def _fake_daily_async_llm(*, matched_arxiv_ids: set[str], assert_prompt=None, fail_arxiv_ids=None):
    fail_arxiv_ids = fail_arxiv_ids or set()

    async def fake_async_call_llm(**kwargs):
        assert kwargs["profile"] == JUDGE_PROFILE
        if assert_prompt:
            assert_prompt(kwargs["user_prompt"])
        arxiv_id = _extract_prompt_arxiv_id(kwargs["user_prompt"])
        if arxiv_id in fail_arxiv_ids:
            raise RuntimeError(f"transient failure for {arxiv_id}")
        is_match = arxiv_id in matched_arxiv_ids
        return {
            "content": {
                "matches": [
                    {
                        "arxivId": arxiv_id,
                        "stance": "supports" if is_match else "irrelevant",
                        "relevanceScore": 0.82 if is_match else 0.0,
                        "confidence": 0.9,
                        "rationale": (
                            "The paper directly addresses the filter."
                            if is_match
                            else "The paper is unrelated to the filter."
                        ),
                        "matchedClaims": ["Relevant claim"] if is_match else [],
                        "abstractEvidence": ["Relevant abstract evidence"] if is_match else [],
                    }
                ]
            },
            "model": "test-model",
            "response_id": f"match-response-{arxiv_id}",
        }

    return fake_async_call_llm


def _fake_summary_llm(*, matched_arxiv_id: str):
    calls = {"count": 0}

    def fake_call_llm(**kwargs):
        assert kwargs["profile"] == SUMMARY_PROFILE
        calls["count"] += 1
        return {
            "content": {
                "summary": "One relevant paper matched today's filters.",
                "citations": [
                    {
                        "paperMatchId": "",
                        "arxivId": matched_arxiv_id,
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
                "mode": "warrants",
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
        monkeypatch.setattr("app.jobs.daily_search.fetch_daily_papers", lambda: daily_papers)
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
        assert updated_run.status == "completed"
        assert updated_run.stage == "completed"
        assert updated_run.summary is not None
        assert updated_run.match_count is not None
        assert updated_run.candidate_count == len(daily_papers)
        assert updated_run.progress_total == len(daily_papers)
        assert updated_run.progress_current == updated_run.progress_total
        assert len(updated_run.progress_log) >= 3

    def test_ignores_archived_filters(self, db_session, db_engine, monkeypatch):
        from sqlalchemy.orm import sessionmaker

        # Create archived filter only
        filt = Filter(
            id=str(uuid.uuid4()),
            name="Archived Filter",
            definition={
                "name": "Archived",
                "description": "Test",
                "mode": "warrants",
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
            "app.jobs.daily_search.fetch_daily_papers",
            lambda: [_paper_fixture("2605.00004", "Fetched Paper")],
        )

        from app.jobs.daily_search import run_daily_search
        run_daily_search(run_id)

        db_session.expire_all()
        updated_run = db_session.query(SearchRun).filter(SearchRun.id == run_id).first()
        assert updated_run.status == "completed"
        assert updated_run.stage == "completed"
        assert updated_run.match_count == 0

    def test_searches_only_fetched_candidate_papers(self, db_session, db_engine, monkeypatch):
        from sqlalchemy.orm import sessionmaker

        filt = Filter(
            id=str(uuid.uuid4()),
            name="Test Filter",
            definition={
                "name": "Test Filter",
                "description": "Neural network scaling laws",
                "mode": "warrants",
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
            "app.jobs.daily_search.fetch_daily_papers",
            lambda: [_paper_fixture("2401.00001", "Included Paper")],
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
                "mode": "warrants",
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
            "app.jobs.daily_search.fetch_daily_papers",
            lambda: [_paper_fixture("2605.00003", "Current Paper")],
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
                "mode": "warrants",
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
        monkeypatch.setattr("app.jobs.daily_search.fetch_daily_papers", lambda: daily_papers)
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
        assert updated_run.status == "completed"
        assert updated_run.progress_current == 2
        assert updated_run.progress_total == 2
        assert updated_run.match_count == 1
        assert any("failed" in entry["message"] for entry in updated_run.progress_log)

    def test_pair_timeout_increments_progress_and_completes(
        self, db_session, db_engine, monkeypatch
    ):
        from sqlalchemy.orm import sessionmaker
        import asyncio

        filt = Filter(
            id=str(uuid.uuid4()),
            name="Test Filter",
            definition={
                "name": "Test Filter",
                "description": "Neural network scaling laws",
                "mode": "warrants",
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
            _paper_fixture("2605.00020", "Successful Paper"),
            _paper_fixture("2605.00021", "Slow Paper"),
        ]
        db_session.commit()

        async def slow_then_match(**kwargs):
            arxiv_id = _extract_prompt_arxiv_id(kwargs["user_prompt"])
            if arxiv_id == "2605.00021":
                await asyncio.sleep(0.05)
            return await _fake_daily_async_llm(matched_arxiv_ids={"2605.00020"})(**kwargs)

        TestSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
        monkeypatch.setattr("app.jobs.daily_search.SessionLocal", TestSession)
        monkeypatch.setattr("app.jobs.daily_search.fetch_daily_papers", lambda: daily_papers)
        monkeypatch.setattr("app.jobs.daily_search.PAIR_TIMEOUT_SECONDS", 0.01)
        monkeypatch.setattr("app.jobs.daily_search.async_call_llm", slow_then_match)
        monkeypatch.setattr(
            "app.jobs.daily_search.call_llm",
            _fake_summary_llm(matched_arxiv_id="2605.00020"),
        )

        from app.jobs.daily_search import run_daily_search
        run_daily_search(run_id)

        db_session.expire_all()
        updated_run = db_session.query(SearchRun).filter(SearchRun.id == run_id).first()
        assert updated_run.status == "completed"
        assert updated_run.progress_current == 2
        assert updated_run.progress_total == 2
        assert updated_run.match_count == 1
        assert any("Timed out" in entry["message"] for entry in updated_run.progress_log)

    def test_all_pair_failures_mark_run_failed(self, db_session, db_engine, monkeypatch):
        from sqlalchemy.orm import sessionmaker

        filt = Filter(
            id=str(uuid.uuid4()),
            name="Test Filter",
            definition={
                "name": "Test Filter",
                "description": "Neural network scaling laws",
                "mode": "warrants",
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
        monkeypatch.setattr("app.jobs.daily_search.fetch_daily_papers", lambda: daily_papers)
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
            assert "All 1 filter-paper evaluations failed" in str(exc)
        else:
            raise AssertionError("Expected all pair failures to fail the run")

        db_session.expire_all()
        updated_run = db_session.query(SearchRun).filter(SearchRun.id == run_id).first()
        assert updated_run.status == "failed"
        assert updated_run.stage == "failed"
        assert updated_run.progress_current == 1
        assert updated_run.progress_total == 1


class TestGenerateIdeaMap:
    def test_marks_unavailable_html_as_skipped(self, db_session, db_engine, monkeypatch):
        from sqlalchemy.orm import sessionmaker

        # Create paper without HTML
        paper_id = str(uuid.uuid4())
        paper = Paper(
            id=paper_id,
            arxiv_id="9999.99999",
            title="Test Paper",
            abstract="Test abstract for paper.",
            authors=["Author"],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(paper)
        db_session.flush()

        idea_map_id = str(uuid.uuid4())
        idea_map = IdeaMap(
            id=idea_map_id,
            paper_id=paper_id,
            status="queued",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(idea_map)
        db_session.commit()

        TestSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
        monkeypatch.setattr("app.jobs.idea_map.SessionLocal", TestSession)

        # Mock httpx to simulate fetch failure
        import httpx

        def mock_get(*args, **kwargs):
            raise httpx.HTTPError("Not found")

        monkeypatch.setattr("httpx.get", mock_get)

        from app.jobs.idea_map import generate_idea_map
        generate_idea_map(idea_map_id)

        db_session.expire_all()
        updated = db_session.query(IdeaMap).filter(IdeaMap.id == idea_map_id).first()
        assert updated.status in ("skipped", "failed")

    def test_uses_cached_html(self, db_session, db_engine, monkeypatch):
        from sqlalchemy.orm import sessionmaker

        paper_id = str(uuid.uuid4())
        paper = Paper(
            id=paper_id,
            arxiv_id="2401.00001",
            title="Test Paper",
            abstract="Test abstract.",
            authors=["Author"],
            html_url="https://arxiv.org/html/2401.00001",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(paper)
        db_session.flush()

        # Pre-cache HTML
        cached_html = PaperHtml(
            paper_id=paper_id,
            source_url="https://arxiv.org/html/2401.00001",
            html="<html><body><p id='p1'>This is a cached paragraph with sufficient text content.</p></body></html>",
            fetched_at=datetime.now(timezone.utc),
        )
        db_session.add(cached_html)
        db_session.flush()

        idea_map_id = str(uuid.uuid4())
        idea_map = IdeaMap(
            id=idea_map_id,
            paper_id=paper_id,
            status="queued",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db_session.add(idea_map)
        db_session.commit()

        TestSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)

        def fake_idea_map_llm(**kwargs):
            assert kwargs["profile"] == IDEA_MAP_PROFILE
            return {
                "content": {
                    "claims": [
                        {
                            "id": "claim-1",
                            "text": "The paper makes a test claim.",
                            "warrants": [
                                {
                                    "id": "warrant-1",
                                    "text": "The cached paragraph supports the claim.",
                                    "citation": {
                                        "blockId": "p1",
                                        "quote": "cached paragraph",
                                        "htmlAnchor": "#p1",
                                    },
                                }
                            ],
                        }
                    ]
                },
                "model": "test-model",
                "response_id": "idea-map-response",
            }

        monkeypatch.setattr("app.jobs.idea_map.SessionLocal", TestSession)
        monkeypatch.setattr(
            "app.jobs.idea_map.call_llm",
            fake_idea_map_llm,
        )

        # Should NOT call httpx.get since HTML is cached
        call_count = {"n": 0}
        original_get = __import__("httpx").get
        def counting_get(*args, **kwargs):
            call_count["n"] += 1
            return original_get(*args, **kwargs)
        monkeypatch.setattr("httpx.get", counting_get)

        from app.jobs.idea_map import generate_idea_map
        generate_idea_map(idea_map_id)

        assert call_count["n"] == 0

        db_session.expire_all()
        updated = db_session.query(IdeaMap).filter(IdeaMap.id == idea_map_id).first()
        assert updated.status in ("completed", "skipped", "failed")
