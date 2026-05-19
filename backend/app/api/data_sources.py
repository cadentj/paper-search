from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.http_errors import raise_http_from_service
from app.db.session import get_db
from app.models.data_source import DataSource
from app.services.sources import ensure_default_data_sources, list_data_sources, update_data_source

router = APIRouter(prefix="/data-sources", tags=["data-sources"])


class DataSourceUpdate(BaseModel):
    enabled: bool | None = None
    settings: dict | None = None


@router.get("", response_model=list[DataSource])
def get_data_sources(db: Session = Depends(get_db)):
    ensure_default_data_sources(db)
    return [source.to_pydantic() for source in list_data_sources(db)]


@router.patch("/{source_type}", response_model=DataSource)
def update_data_source_route(
    source_type: str,
    request: DataSourceUpdate,
    db: Session = Depends(get_db),
):
    try:
        source = update_data_source(
            db,
            source_type,
            enabled=request.enabled,
            settings=request.settings,
        )
    except Exception as exc:
        raise_http_from_service(exc)
    return source.to_pydantic()
