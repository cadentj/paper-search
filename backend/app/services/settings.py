from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.app_setting import AppSetting

DAILY_SCHEDULE_KEY = "daily_search_schedule"


def get_daily_schedule(db: Session) -> dict:
    setting = db.query(AppSetting).filter(AppSetting.key == DAILY_SCHEDULE_KEY).first()
    if not setting:
        return {"time": None, "enabled": False}
    return dict(setting.value)


def update_daily_schedule(db: Session, data: dict) -> dict:
    now = datetime.now(timezone.utc)
    setting = db.query(AppSetting).filter(AppSetting.key == DAILY_SCHEDULE_KEY).first()
    if setting:
        setting.value = data
        setting.updated_at = now
    else:
        setting = AppSetting(key=DAILY_SCHEDULE_KEY, value=data, updated_at=now)
        db.add(setting)
    db.flush()
    db.refresh(setting)
    return dict(setting.value)
