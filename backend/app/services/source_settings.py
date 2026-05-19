from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.data_source import DataSource


DEFAULT_SOURCES = {
    "arxiv": {
        "name": "arXiv",
        "enabled": True,
        "settings": {},
    },
    "lesswrong": {
        "name": "LessWrong",
        "enabled": False,
        "settings": {
            "view": "new",
        },
    },
}


def ensure_default_data_sources(db: Session) -> list[DataSource]:
    for source_type, defaults in DEFAULT_SOURCES.items():
        existing = db.query(DataSource).filter(DataSource.source_type == source_type).first()
        if existing:
            continue
        now = datetime.now(timezone.utc)
        db.add(
            DataSource(
                source_type=source_type,
                name=defaults["name"],
                enabled=defaults["enabled"],
                settings=defaults["settings"],
                created_at=now,
                updated_at=now,
            )
        )
    db.flush()
    return list_data_sources(db)


def list_data_sources(db: Session) -> list[DataSource]:
    sources = db.query(DataSource).order_by(DataSource.name.asc()).all()
    order = {"arxiv": 0, "lesswrong": 1}
    return sorted(sources, key=lambda source: order.get(source.source_type, 99))


def enabled_source_types(db: Session) -> set[str]:
    return {
        source.source_type
        for source in ensure_default_data_sources(db)
        if source.enabled
    }
