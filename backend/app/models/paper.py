from datetime import datetime
from typing import Optional

from pydantic import BaseModel
from paper_search_core.models.paper import Paper as _Paper

SQLAPaper = _Paper


class Paper(BaseModel):
    id: str
    source_type: str = "arxiv"
    source_id: Optional[str] = None
    title: str
    search_text: str
    authors: list
    published_at: Optional[datetime] = None
    html_url: Optional[str] = None
    source_url: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


def to_pydantic(self) -> Paper:
    return Paper.model_validate(self)


SQLAPaper.to_pydantic = to_pydantic  # type: ignore[method-assign]

__all__ = ["SQLAPaper", "Paper"]
