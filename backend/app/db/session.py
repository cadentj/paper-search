import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import settings


def _get_db_path(url: str) -> str:
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "")
    return ""


def get_engine(url: str | None = None):
    db_url = url or settings.DATABASE_URL
    db_path = _get_db_path(db_url)
    if db_path:
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False} if db_url.startswith("sqlite") else {},
        pool_pre_ping=True,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
