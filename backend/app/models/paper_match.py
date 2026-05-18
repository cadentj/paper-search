from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, ForeignKey, Text

from app.models.base import Base
from app.schemas.search import PaperMatchResponse
from paper_search_core.schemas.daily_search import paper_item_label

if TYPE_CHECKING:
    from app.models.filter import Filter
    from app.models.paper import Paper


class PaperMatch(Base):
    __tablename__ = "paper_matches"

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    search_run_id = Column(Text, ForeignKey("search_runs.id"), nullable=False)
    filter_id = Column(Text, ForeignKey("filters.id"), nullable=False)
    paper_id = Column(Text, ForeignKey("papers.id"), nullable=False)

    result = Column(Text, nullable=False)

    llm_model = Column(Text, nullable=True)
    llm_response_id = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    def to_pydantic(
        self,
        *,
        paper: Paper | None = None,
        filt: Filter | None = None,
    ) -> PaperMatchResponse:
        return PaperMatchResponse(
            id=self.id,
            search_run_id=self.search_run_id,
            filter_id=self.filter_id,
            paper_id=self.paper_id,
            result=self.result,
            llm_model=self.llm_model,
            created_at=self.created_at,
            paper_title=paper.title if paper else None,
            paper_authors=paper.authors if paper else None,
            paper_source_type=paper.source_type if paper else None,
            paper_source_id=paper.source_id if paper else None,
            paper_source_url=paper.source_url if paper else None,
            paper_item_label=paper_item_label(paper) if paper else None,
            paper_abstract=paper.abstract if paper else None,
            filter_name=filt.name if filt else None,
        )
