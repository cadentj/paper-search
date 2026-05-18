"""Test fixtures for backend tests."""

import os

import pytest

# Fill required public base URLs when .env leaves them empty.
for _key, _default in (
    ("ARXIV_HTML_PUBLIC_BASE_URL", "https://example.com/arxiv/"),
    ("LESSWRONG_HTML_PUBLIC_BASE_URL", "https://example.com/lesswrong/"),
):
    if not os.environ.get(_key, "").strip():
        os.environ[_key] = _default
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.models.base import Base


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
        cursor.close()

    # Import all models so they register with Base
    import app.models.filter
    import app.models.job
    import app.models.onboarding_extraction
    import app.models.paper
    import app.models.search_run
    import app.models.search_run_paper
    import app.models.paper_match
    import app.models.idea_map
    import app.models.source_daily

    Base.metadata.create_all(bind=engine)
    from app.db.schema import ensure_runtime_schema

    ensure_runtime_schema(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    """Create a database session for testing."""
    Session = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def client(db_engine, monkeypatch):
    """Create a FastAPI test client with a test database."""
    from sqlalchemy.orm import sessionmaker
    Session = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    # Must import after engine setup
    from app.main import app
    from app.db.session import get_db
    from fastapi.testclient import TestClient

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()
