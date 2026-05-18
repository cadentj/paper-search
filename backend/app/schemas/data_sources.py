from datetime import datetime

from pydantic import BaseModel


class DataSourceResponse(BaseModel):
    id: str
    source_type: str
    name: str
    enabled: bool
    settings: dict
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UpdateDataSourceRequest(BaseModel):
    enabled: bool | None = None
    settings: dict | None = None
