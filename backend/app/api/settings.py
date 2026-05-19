from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import settings as settings_service

router = APIRouter(prefix="/settings", tags=["settings"])


class DailySchedule(BaseModel):
    time: Optional[str] = None
    enabled: bool = False


class DailyScheduleUpdate(BaseModel):
    time: Optional[str] = None
    enabled: bool = False


@router.get("/daily-schedule", response_model=DailySchedule)
def get_daily_schedule(db: Session = Depends(get_db)):
    return DailySchedule(**settings_service.get_daily_schedule(db))


@router.put("/daily-schedule", response_model=DailySchedule)
def update_daily_schedule(body: DailyScheduleUpdate, db: Session = Depends(get_db)):
    value = settings_service.update_daily_schedule(db, body.model_dump())
    return DailySchedule(**value)
