from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.data_source import DataSource
from app.schemas.data_sources import DataSourceResponse, UpdateDataSourceRequest
from app.services.source_settings import ensure_default_data_sources, list_data_sources

router = APIRouter(prefix="/data-sources", tags=["data-sources"])


@router.get("", response_model=list[DataSourceResponse])
def get_data_sources(db: Session = Depends(get_db)):
    ensure_default_data_sources(db)
    return list_data_sources(db)


@router.patch("/{source_type}", response_model=DataSourceResponse)
def update_data_source(
    source_type: str,
    request: UpdateDataSourceRequest,
    db: Session = Depends(get_db),
):
    ensure_default_data_sources(db)
    source = db.query(DataSource).filter(DataSource.source_type == source_type).first()
    if not source:
        raise HTTPException(status_code=404, detail="Data source not found")

    if request.enabled is not None:
        source.enabled = request.enabled
    if request.settings is not None:
        source.settings = {**(source.settings or {}), **request.settings}
    source.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(source)
    return source
