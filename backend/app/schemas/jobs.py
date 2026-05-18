from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.documents import DocumentResponse
from app.schemas.filters import FilterResponse
from app.schemas.onboarding import OnboardingExtractionResponse
from app.schemas.papers import IdeaMapResponse
from app.schemas.search import PaperMatchResponse, SearchRunResponse


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


class JobStartResponse(BaseModel):
    job_id: str


class DailySearchJobResponse(BaseModel):
    job: JobResponse
    subject: SearchRunResponse
    items: list[PaperMatchResponse] = Field(default_factory=list)
    next_cursor: str | None = None
    done: bool = False


class IdeaMapJobResponse(BaseModel):
    job: JobResponse
    subject: IdeaMapResponse
    items: list[dict] = Field(default_factory=list)
    next_cursor: str | None = None
    done: bool = False


class OnboardingGenerationJobResponse(BaseModel):
    job: JobResponse
    subject: JobResponse
    items: list[FilterResponse] = Field(default_factory=list)
    next_cursor: str | None = None
    done: bool = False


class OnboardingExtractionJobResponse(BaseModel):
    job: JobResponse
    subject: OnboardingExtractionResponse
    items: list[dict] = Field(default_factory=list)
    next_cursor: str | None = None
    done: bool = False


class DocumentProcessingJobResponse(BaseModel):
    job: JobResponse
    subject: DocumentResponse
    items: list[dict] = Field(default_factory=list)
    next_cursor: str | None = None
    done: bool = False
