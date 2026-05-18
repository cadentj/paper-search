from paper_search_core.models.paper import Paper as _Paper

from app.schemas.papers import PaperResponse

Paper = _Paper


def to_pydantic(self) -> PaperResponse:
    return PaperResponse.model_validate(self)


Paper.to_pydantic = to_pydantic  # type: ignore[method-assign]

__all__ = ["Paper"]
