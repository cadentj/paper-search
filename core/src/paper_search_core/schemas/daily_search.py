from pydantic import BaseModel


class PaperPayload(BaseModel):
    id: str
    title: str
    source_type: str
    source_id: str
    item_id: str
    text: str
    authors: list[str]

    def prompt_text(self) -> str:
        authors = ", ".join(self.authors) if self.authors else "Unknown"
        return (
            f"Item ID: {self.item_id}\n"
            f"Source Type: {self.source_type}\n"
            f"Source ID: {self.source_id}\n"
            f"Title: {self.title}\n"
            f"Authors: {authors}\n"
            f"Excerpt: {self.text}\n"
        )

class PaperMatchPayload(BaseModel):
    match_id: str
    paper: PaperPayload
    filter_name: str
    result: str

    def prompt_text(self) -> str:
        return (
            f"{self.paper.prompt_text()}"
            f"Filter: {self.filter_name}\n"
            f"Result: {self.result}\n"
            f"Match ID: {self.match_id}\n"
        )

    @classmethod
    def join_prompt_text(
        cls, matches: list["PaperMatchPayload"], sep: str = "\n---\n"
    ) -> str:
        return sep.join(m.prompt_text() for m in matches)


def paper_item_id(source_type: str, source_id: str) -> str:
    return f"{source_type}:{source_id}"


def paper_item_label(paper) -> str:
    source_type = paper.source_type or "arxiv"
    source_id = paper.source_id or paper.id
    return paper_item_id(source_type, source_id)
