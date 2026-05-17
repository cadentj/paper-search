"""Worker job tests against temporary SQLite database."""

import uuid
from datetime import datetime, timezone

from app.models.filter import Filter
from app.models.onboarding_extraction import OnboardingExtraction
from app.models.paper import Paper
from app.models.search_run import SearchRun
from app.models.idea_map import IdeaMap
from app.models.paper_html import PaperHtml
from app.services.mock_papers import get_daily_papers


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
        monkeypatch.setattr("app.jobs.onboarding.SessionLocal", TestSession)
        monkeypatch.setattr("app.core.config.settings.OPENROUTER_API_KEY", "")

        from app.jobs.onboarding import extract_onboarding_filters
        extract_onboarding_filters(ext_id)

        db_session.expire_all()
        updated = db_session.query(OnboardingExtraction).filter(
            OnboardingExtraction.id == ext_id
        ).first()
        assert updated.status == "completed"
        assert updated.proposed_filters is not None
        assert len(updated.proposed_filters) > 0


class TestRunDailySearch:
    def test_persists_matches_and_summary(self, db_session, db_engine, monkeypatch):
        from sqlalchemy.orm import sessionmaker

        # Create active filter
        filt = Filter(
            id=str(uuid.uuid4()),
            name="Test Filter",
            definition={
                "name": "Test Filter",
                "statement": "Neural network scaling laws",
                "search": {"instructions": "Find evidence", "outputMode": "warrants"},
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

        # Create papers from mock provider
        daily_papers = get_daily_papers()
        for p_data in daily_papers:
            paper = Paper(
                id=str(uuid.uuid4()),
                arxiv_id=p_data["arxiv_id"],
                title=p_data["title"],
                abstract=p_data["abstract"],
                authors=p_data["authors"],
                categories=p_data.get("categories"),
                published_at=p_data.get("published_at"),
                html_url=p_data.get("html_url"),
                landing_url=p_data.get("landing_url"),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db_session.add(paper)

        db_session.commit()

        # Patch SessionLocal
        TestSession = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
        monkeypatch.setattr("app.jobs.daily_search.SessionLocal", TestSession)
        monkeypatch.setattr("app.core.config.settings.OPENROUTER_API_KEY", "")

        from app.jobs.daily_search import run_daily_search
        run_daily_search(run_id)

        db_session.expire_all()
        updated_run = db_session.query(SearchRun).filter(SearchRun.id == run_id).first()
        assert updated_run.status == "completed"
        assert updated_run.summary is not None
        assert updated_run.match_count is not None

    def test_ignores_archived_filters(self, db_session, db_engine, monkeypatch):
        from sqlalchemy.orm import sessionmaker

        # Create archived filter only
        filt = Filter(
            id=str(uuid.uuid4()),
            name="Archived Filter",
            definition={
                "name": "Archived",
                "statement": "Test",
                "search": {"instructions": "Test", "outputMode": "warrants"},
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
        monkeypatch.setattr("app.core.config.settings.OPENROUTER_API_KEY", "")

        from app.jobs.daily_search import run_daily_search
        run_daily_search(run_id)

        db_session.expire_all()
        updated_run = db_session.query(SearchRun).filter(SearchRun.id == run_id).first()
        assert updated_run.status == "completed"
        assert updated_run.match_count == 0


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
        monkeypatch.setattr("app.jobs.idea_map.SessionLocal", TestSession)
        monkeypatch.setattr("app.core.config.settings.OPENROUTER_API_KEY", "")

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
