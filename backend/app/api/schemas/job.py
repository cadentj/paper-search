from typing import Generic, TypeVar

from pydantic import BaseModel, Field

from app.models.job import Job

SubjectT = TypeVar("SubjectT")
ItemT = TypeVar("ItemT")


class JobStart(BaseModel):
    job_id: str


class JobPoll(BaseModel, Generic[SubjectT, ItemT]):
    job: Job
    subject: SubjectT
    items: list[ItemT] = Field(default_factory=list)
    next_cursor: str | None = None
    done: bool = False
