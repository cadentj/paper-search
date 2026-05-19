from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.app_setting import AppSetting

router = APIRouter(prefix="/settings", tags=["settings"])


class DailyScheduleResponse(BaseModel):
    time: Optional[str] = None  # HH:MM format, e.g. "09:00"
    enabled: bool = False


class DailyScheduleUpdate(BaseModel):
    time: Optional[str] = None
    enabled: bool = False


DAILY_SCHEDULE_KEY = "daily_search_schedule"


@router.get("/daily-schedule", response_model=DailyScheduleResponse)
def get_daily_schedule(db: Session = Depends(get_db)):
    setting = db.query(AppSetting).filter(AppSetting.key == DAILY_SCHEDULE_KEY).first()
    if not setting:
        return DailyScheduleResponse()
    return DailyScheduleResponse(**setting.value)


@router.put("/daily-schedule", response_model=DailyScheduleResponse)
def update_daily_schedule(body: DailyScheduleUpdate, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    setting = db.query(AppSetting).filter(AppSetting.key == DAILY_SCHEDULE_KEY).first()
    data = body.model_dump()

    if setting:
        setting.value = data
        setting.updated_at = now
    else:
        setting = AppSetting(key=DAILY_SCHEDULE_KEY, value=data, updated_at=now)
        db.add(setting)

    db.commit()
    db.refresh(setting)
    return DailyScheduleResponse(**setting.value)
