"""Unit tests for Database.session() transaction behavior."""

import uuid
from datetime import datetime, timezone

import pytest

from app.db.session import Database
from app.models.filter import SQLAFilter


@pytest.fixture
def isolated_database(db_engine):
    return Database(db_engine)


def test_session_commits_on_success(isolated_database):
    filt_id = str(uuid.uuid4())
    with isolated_database.session() as db:
        db.add(
            SQLAFilter(
                id=filt_id,
                name="Committed SQLAFilter",
                definition={
                    "name": "Committed SQLAFilter",
                    "description": "",
                    "mode": "topic",
                },
                status="active",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )

    with isolated_database.session() as db:
        filter = db.query(SQLAFilter).filter(SQLAFilter.id == filt_id).first()
        assert filter is not None
        assert filter.name == "Committed SQLAFilter"


def test_session_rolls_back_on_exception(isolated_database):
    filt_id = str(uuid.uuid4())
    with pytest.raises(ValueError):
        with isolated_database.session() as db:
            db.add(
                SQLAFilter(
                    id=filt_id,
                    name="Rolled Back",
                    definition={
                        "name": "Rolled Back",
                        "description": "",
                        "mode": "topic",
                    },
                    status="active",
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
            )
            raise ValueError("abort")

    with isolated_database.session() as db:
        assert db.query(SQLAFilter).filter(SQLAFilter.id == filt_id).first() is None


def test_explicit_commit_inside_session_is_harmless(isolated_database):
    filt_id = str(uuid.uuid4())
    with isolated_database.session() as db:
        db.add(
            SQLAFilter(
                id=filt_id,
                name="Double Commit",
                definition={
                    "name": "Double Commit",
                    "description": "",
                    "mode": "topic",
                },
                status="active",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        db.commit()

    with isolated_database.session() as db:
        assert db.query(SQLAFilter).filter(SQLAFilter.id == filt_id).first() is not None
