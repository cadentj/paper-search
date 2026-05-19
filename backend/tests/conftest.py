"""Test fixtures for backend tests."""

import importlib
import os

import pytest

# Fill required public base URLs when .env leaves them empty.
for _key, _default in (
    ("ARXIV_HTML_PUBLIC_BASE_URL", "https://example.com/arxiv/"),
    ("LESSWRONG_HTML_PUBLIC_BASE_URL", "https://example.com/lesswrong/"),
):
    if not os.environ.get(_key, "").strip():
        os.environ[_key] = _default
from sqlalchemy import create_engine, event, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.db.session import Database  # noqa: E402
from app.models.base import Base  # noqa: E402


@pytest.fixture
def db_engine(tmp_path):
    """Create a temporary SQLite database engine."""
    db_path = tmp_path / "test.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    # Import all models so they register with Base
    import app.models.app_setting  # noqa: F401
    import app.models.filter  # noqa: F401
    import app.models.job  # noqa: F401
    import app.models.onboarding_extraction  # noqa: F401
    import paper_search_core.models.paper  # noqa: F401
    import app.models.search_run  # noqa: F401
    import app.models.paper_match  # noqa: F401
    import app.models.paper_match_feedback  # noqa: F401
    import app.models.paper_note  # noqa: F401
    import app.models.idea_map  # noqa: F401

    Base.metadata.create_all(bind=engine)
    from app.services.papers_fts import ensure_papers_fts

    ensure_papers_fts(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT OR IGNORE INTO app_settings (key, value, updated_at)
                VALUES (
                    'data_sources',
                    '{"arxiv": {"enabled": true, "settings": {}}, "lesswrong": {"enabled": false, "settings": {"view": "new"}}}',
                    datetime('now')
                )
                """
            )
        )
    yield engine
    engine.dispose()


@pytest.fixture
def test_database(db_engine):
    """Test Database wrapper around the temporary engine."""
    return Database(db_engine)


@pytest.fixture
def db_session(db_engine):
    """Long-lived session for test setup assertions (avoids SQLite lock vs workers)."""
    Session = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = Session()
    yield session
    session.close()


_WORKER_DATABASE_MODULES = (
    "app.jobs.dispatcher",
    "app.jobs.daily_search",
    "app.jobs.daily_search_summary",
    "app.jobs.documents",
    "app.jobs.feedback_reflection",
    "app.jobs.idea_map",
    "app.jobs.onboarding",
    "app.jobs.scholar_import",
)


@pytest.fixture
def patch_worker_database(monkeypatch, test_database):
    """Point app workers at the test database (patch use-sites, not only session)."""
    monkeypatch.setattr("app.db.session.database", test_database)
    for module_name in _WORKER_DATABASE_MODULES:
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        monkeypatch.setattr(module, "database", test_database, raising=False)


@pytest.fixture
def client(test_database):
    """Create a FastAPI test client with a test database."""

    def override_get_db():
        with test_database.session() as db:
            yield db

    # Must import after engine setup
    from app.main import app
    from app.db.session import get_db
    from fastapi.testclient import TestClient

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()
