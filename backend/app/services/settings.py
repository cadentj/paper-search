from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.app_setting import SQLAAppSetting
from app.services.errors import NotFound

DAILY_SCHEDULE_KEY = "daily_search_schedule"
DATA_SOURCES_KEY = "data_sources"

SOURCE_CATALOG: dict[str, dict[str, Any]] = {
    "arxiv": {
        "name": "arXiv",
        "enabled": True,
        "settings": {},
    },
    "lesswrong": {
        "name": "LessWrong",
        "enabled": False,
        "settings": {"view": "new"},
    },
}

SOURCE_ORDER = ("arxiv", "lesswrong")


def get_daily_schedule(db: Session) -> dict:
    setting = (
        db.query(SQLAAppSetting)
        .filter(SQLAAppSetting.key == DAILY_SCHEDULE_KEY)
        .first()
    )
    if not setting:
        return {"time": None, "enabled": False}
    return dict(setting.value)


def update_daily_schedule(db: Session, data: dict) -> dict:
    now = datetime.now(timezone.utc)
    setting = (
        db.query(SQLAAppSetting)
        .filter(SQLAAppSetting.key == DAILY_SCHEDULE_KEY)
        .first()
    )
    if setting:
        setting.value = data
        setting.updated_at = now
    else:
        setting = SQLAAppSetting(key=DAILY_SCHEDULE_KEY, value=data, updated_at=now)
        db.add(setting)
    db.flush()
    db.refresh(setting)
    return dict(setting.value)


def _default_data_sources_value() -> dict[str, dict[str, Any]]:
    return {
        source_type: {
            "enabled": meta["enabled"],
            "settings": deepcopy(meta["settings"]),
        }
        for source_type, meta in SOURCE_CATALOG.items()
    }


def _get_stored_data_sources(db: Session) -> dict[str, dict[str, Any]]:
    setting = (
        db.query(SQLAAppSetting).filter(SQLAAppSetting.key == DATA_SOURCES_KEY).first()
    )
    if not setting:
        return _default_data_sources_value()
    stored = dict(setting.value)
    merged = _default_data_sources_value()
    for source_type in SOURCE_CATALOG:
        if source_type in stored:
            row = stored[source_type]
            merged[source_type] = {
                "enabled": bool(row.get("enabled", merged[source_type]["enabled"])),
                "settings": {
                    **merged[source_type]["settings"],
                    **(row.get("settings") or {}),
                },
            }
    return merged


def _save_data_sources(db: Session, value: dict[str, dict[str, Any]]) -> None:
    now = datetime.now(timezone.utc)
    setting = (
        db.query(SQLAAppSetting).filter(SQLAAppSetting.key == DATA_SOURCES_KEY).first()
    )
    if setting:
        setting.value = value
        setting.updated_at = now
    else:
        db.add(SQLAAppSetting(key=DATA_SOURCES_KEY, value=value, updated_at=now))
    db.flush()


def _data_source_view(source_type: str, row: dict[str, Any]) -> dict[str, Any]:
    meta = SOURCE_CATALOG[source_type]
    return {
        "source_type": source_type,
        "name": meta["name"],
        "enabled": row["enabled"],
        "settings": row["settings"],
    }


def get_data_sources(db: Session) -> list[dict[str, Any]]:
    stored = _get_stored_data_sources(db)
    return [
        _data_source_view(source_type, stored[source_type])
        for source_type in SOURCE_ORDER
    ]


def update_data_source(
    db: Session,
    source_type: str,
    *,
    enabled: bool | None = None,
    settings: dict | None = None,
) -> dict[str, Any]:
    if source_type not in SOURCE_CATALOG:
        raise NotFound("Data source not found")

    stored = _get_stored_data_sources(db)
    row = stored[source_type]
    if enabled is not None:
        row["enabled"] = enabled
    if settings is not None:
        row["settings"] = {**row["settings"], **settings}
    _save_data_sources(db, stored)
    return _data_source_view(source_type, row)


def enabled_source_types(db: Session) -> set[str]:
    stored = _get_stored_data_sources(db)
    return {
        source_type for source_type in SOURCE_CATALOG if stored[source_type]["enabled"]
    }
