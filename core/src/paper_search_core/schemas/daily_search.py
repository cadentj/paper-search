from pydantic import BaseModel

# Bounds for daily summary LLM prompts (full paper excerpts blow past context limits).
SUMMARY_PAPER_EXCERPT_MAX_CHARS = 600
SUMMARY_MATCH_RESULT_MAX_CHARS = 400
SUMMARY_MATCHES_TEXT_MAX_CHARS = 28_000


def _truncate_for_summary(text: str, max_chars: int) -> str:
    cleaned = text.strip()
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3].rstrip() + "..."


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
    filter_mode: str
    filter_description: str
    result: str

    def prompt_text(self) -> str:
        return (
            f"{self.paper.prompt_text()}"
            f"Filter mode: {self.filter_mode}\n"
            f"Filter: {self.filter_name}\n"
            f"Filter description: {self.filter_description}\n"
            f"Result: {self.result}\n"
            f"Match ID: {self.match_id}\n"
        )

    def summary_prompt_text(self) -> str:
        authors = ", ".join(self.paper.authors) if self.paper.authors else "Unknown"
        excerpt = _truncate_for_summary(
            self.paper.text, SUMMARY_PAPER_EXCERPT_MAX_CHARS
        )
        result = _truncate_for_summary(self.result, SUMMARY_MATCH_RESULT_MAX_CHARS)
        return (
            f"Item ID: {self.paper.item_id}\n"
            f"Source Type: {self.paper.source_type}\n"
            f"Source ID: {self.paper.source_id}\n"
            f"Title: {self.paper.title}\n"
            f"Authors: {authors}\n"
            f"Excerpt: {excerpt}\n"
            f"Filter mode: {self.filter_mode}\n"
            f"Filter: {self.filter_name}\n"
            f"Filter description: {self.filter_description}\n"
            f"Result: {result}\n"
            f"Match ID: {self.match_id}\n"
        )

    @classmethod
    def join_prompt_text(
        cls, matches: list["PaperMatchPayload"], sep: str = "\n---\n"
    ) -> str:
        return sep.join(m.prompt_text() for m in matches)

    @classmethod
    def format_grouped_for_summary(cls, matches: list["PaperMatchPayload"]) -> str:
        """Group matches by filter for daily summary prompts (claims before topics)."""
        from collections import defaultdict

        groups: dict[tuple[str, str, str], list[PaperMatchPayload]] = defaultdict(list)
        for payload in matches:
            key = (
                payload.filter_mode,
                payload.filter_name,
                payload.filter_description,
            )
            groups[key].append(payload)

        mode_rank = {"claim": 0, "topic": 1}
        ordered = sorted(
            groups.items(),
            key=lambda item: (mode_rank.get(item[0][0], 2), item[0][1].lower()),
        )

        blocks: list[str] = []
        for (mode, name, description), group_matches in ordered:
            header = (
                f"Filter mode: {mode}\n"
                f"Filter name: {name}\n"
                f"Filter description: {description}\n"
                "Matches:"
            )
            match_blocks = [match.summary_prompt_text() for match in group_matches]
            blocks.append(header + "\n" + "\n---\n".join(match_blocks))

        full_text = "\n\n===\n\n".join(blocks)
        if len(full_text) <= SUMMARY_MATCHES_TEXT_MAX_CHARS:
            return full_text
        return (
            full_text[: SUMMARY_MATCHES_TEXT_MAX_CHARS - 64].rstrip()
            + "\n\n[Match listing truncated for length; summarize all filters above.]"
        )


def paper_item_id(source_type: str, source_id: str) -> str:
    return f"{source_type}:{source_id}"


def paper_item_label(paper) -> str:
    source_type = paper.source_type or "arxiv"
    source_id = paper.source_id or paper.id
    return paper_item_id(source_type, source_id)
