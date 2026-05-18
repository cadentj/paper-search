from pydantic import BaseModel


class PaperPayload(BaseModel):
    id: str
    title: str
    source_type: str
    source_id: str
    item_id: str
    text: str
    authors: list[str]


def paper_item_id(source_type: str, source_id: str) -> str:
    return f"{source_type}:{source_id}"


def paper_item_label(paper) -> str:
    source_type = paper.source_type or "arxiv"
    source_id = paper.source_id or paper.id
    return paper_item_id(source_type, source_id)
