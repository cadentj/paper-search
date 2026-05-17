from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class FeedbackCreate(BaseModel):
    target_type: str  # "filter" | "paper_match" | "idea_map_claim" | "idea_map_warrant"
    target_id: str
    value: str  # "upvote" | "downvote" | "not_interested"
    note: Optional[str] = None


class FeedbackResponse(BaseModel):
    id: str
    target_type: str
    target_id: str
    value: str
    note: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
