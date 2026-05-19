import os
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings


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
        connect_args={"check_same_thread": False}
        if db_url.startswith("sqlite")
        else {},
        pool_pre_ping=True,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    return engine


class Database:
    def __init__(self, engine):
        self.engine = engine
        self.sessionmaker = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        db = self.sessionmaker()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


engine = get_engine()
database = Database(engine)


def get_db():
    with database.session() as db:
        yield db
