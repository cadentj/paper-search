from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.http_errors import raise_http_from_service
from app.db.session import get_db
from app.services import settings as settings_service

router = APIRouter(prefix="/settings", tags=["settings"])


class DailySchedule(BaseModel):
    time: Optional[str] = None
    enabled: bool = False


class DailyScheduleUpdate(BaseModel):
    time: Optional[str] = None
    enabled: bool = False


class DataSource(BaseModel):
    source_type: str
    name: str
    enabled: bool
    settings: dict


class DataSourceUpdate(BaseModel):
    enabled: bool | None = None
    settings: dict | None = None


@router.get("/daily-schedule", response_model=DailySchedule)
def get_daily_schedule(db: Session = Depends(get_db)):
    return DailySchedule(**settings_service.get_daily_schedule(db))


@router.put("/daily-schedule", response_model=DailySchedule)
def update_daily_schedule(body: DailyScheduleUpdate, db: Session = Depends(get_db)):
    value = settings_service.update_daily_schedule(db, body.model_dump())
    return DailySchedule(**value)


@router.get("/data-sources", response_model=list[DataSource])
def get_data_sources(db: Session = Depends(get_db)):
    return [DataSource(**row) for row in settings_service.get_data_sources(db)]


@router.patch("/data-sources/{source_type}", response_model=DataSource)
def update_data_source_route(
    source_type: str,
    body: DataSourceUpdate,
    db: Session = Depends(get_db),
):
    try:
        row = settings_service.update_data_source(
            db,
            source_type,
            enabled=body.enabled,
            settings=body.settings,
        )
    except Exception as exc:
        raise_http_from_service(exc)
    return DataSource(**row)
