import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel
from sqlalchemy import Column, DateTime, JSON, Text

from app.models.base import Base


class ProposedFilter(BaseModel):
    id: str
    name: str
    description: str
    mode: Literal["claim", "topic"] = "topic"


class OnboardingExtraction(BaseModel):
    id: str
    job_id: Optional[str] = None
    status: str
    input_text: str
    proposed_filters: list[ProposedFilter | dict]
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SQLAOnboardingExtraction(Base):
    __tablename__ = "onboarding_extractions"

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    status = Column(Text, nullable=False, default="queued")

    input_text = Column(Text, nullable=False)
    proposed_filters = Column(JSON, nullable=False, default=list)
    error = Column(Text, nullable=True)

    llm_model = Column(Text, nullable=True)
    llm_response_id = Column(Text, nullable=True)

    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    completed_at = Column(DateTime, nullable=True)

    def to_pydantic(self, *, job_id: str | None = None) -> OnboardingExtraction:
        resp = OnboardingExtraction.model_validate(self)
        if job_id is not None:
            return resp.model_copy(update={"job_id": job_id})
        return resp
