from pydantic import BaseModel


class FilterPayload(BaseModel):
    id: str
    name: str
    definition: dict


class PairEvaluation(BaseModel):
    filter_id: str
    filter_name: str
    paper_id: str
    paper_title: str
    source_type: str
    source_id: str
    item_id: str
    result: dict | None = None
    model: str | None = None
    response_id: str | None = None
    error: str | None = None
