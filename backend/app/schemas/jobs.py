from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class JobProgress(BaseModel):
    stage: str = "queued"
    current: int = 0
    total: int = 1
    message: str = "Queued"
    log: list[dict] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class JobResponse(BaseModel):
    id: str
    kind: str
    status: str
    subject_type: str | None = None
    subject_id: str | None = None
    queue_name: str | None = None
    queue_job_id: str | None = None
    progress: dict = Field(default_factory=dict)
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
