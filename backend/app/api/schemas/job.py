from pydantic import BaseModel, ConfigDict


class JobProgress(BaseModel):
    current: int = 0
    total: int = 1

    model_config = ConfigDict(extra="allow")


class JobStart(BaseModel):
    job_id: str
