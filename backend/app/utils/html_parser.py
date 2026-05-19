"""Parse arXiv HTML into addressable blocks for idea map generation."""

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup, Tag


@dataclass
class HtmlBlock:
    block_id: str
    order_index: int
    tag: str
    text: str
    section_title: str = ""
    html_anchor: str = ""


MAX_CITATION_RANGE_BLOCKS = 3
MAX_PROMPT_BLOCKS = 250
BACK_MATTER_RE = re.compile(
    r"\b(appendix|references|acknowledgements|acknowledgments|supplementary|supplemental)\b",
    re.IGNORECASE,
)
ALWAYS_ADDRESSABLE_TAGS = {
    "p",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "td",
    "th",
    "figcaption",
    "blockquote",
}
CONTENT_TAGS = ALWAYS_ADDRESSABLE_TAGS | {"li"}


def parse_arxiv_html(
    html: str, *, exclude_back_matter: bool = False
) -> list[HtmlBlock]:
    """Parse arXiv HTML into addressable blocks preserving section titles."""
    return _parse_arxiv_html_document(html, exclude_back_matter=exclude_back_matter)[0]


def prepare_arxiv_html_for_viewer(html: str, source_url: str | None = None) -> str:
    """Inject canonical block markers and a base URL so arXiv assets resolve in srcDoc."""
    _, soup = _parse_arxiv_html_document(html, exclude_back_matter=False)
    if source_url:
        head = soup.find("head")
        if not head:
            head = soup.new_tag("head")
            html_tag = soup.find("html")
            if html_tag:
                html_tag.insert(0, head)
            else:
                soup.insert(0, head)
        bases = soup.find_all("base")
        base = bases[0] if bases else None
        for duplicate in bases[1:]:
            duplicate.decompose()
        if not base:
            base = soup.new_tag("base")
            head.insert(0, base)
        elif base.parent != head:
            base.extract()
            head.insert(0, base)
        base["href"] = source_url
    return str(soup)


def validate_citation(blocks: list[HtmlBlock], citation: dict) -> bool:
    """Validate a warrant citation against parsed block ranges."""
    return citation_validation_diagnostics(blocks, citation)["valid"]


def citation_validation_diagnostics(blocks: list[HtmlBlock], citation: dict) -> dict:
    """Return validation status plus concise diagnostics for logging."""
    start_block_id = citation.get("startBlockId", "")
    end_block_id = citation.get("endBlockId", "")
    block_map = {b.block_id: b for b in blocks}
    start_block = block_map.get(start_block_id)
    end_block = block_map.get(end_block_id)

    if not start_block_id:
        return _invalid_range("missing_start_block_id", citation, len(blocks))
    if not end_block_id:
        return _invalid_range("missing_end_block_id", citation, len(blocks))
    if not start_block:
        return _invalid_range("start_block_id_not_found", citation, len(blocks))
    if not end_block:
        return _invalid_range("end_block_id_not_found", citation, len(blocks))
    if start_block.order_index > end_block.order_index:
        return _invalid_range(
            "start_block_after_end_block",
            citation,
            len(blocks),
            start_block=start_block,
            end_block=end_block,
        )

    range_length = end_block.order_index - start_block.order_index + 1
    if range_length > MAX_CITATION_RANGE_BLOCKS:
        return _invalid_range(
            "range_too_large",
            citation,
            len(blocks),
            start_block=start_block,
            end_block=end_block,
            rangeLength=range_length,
            maxRangeLength=MAX_CITATION_RANGE_BLOCKS,
        )

    return {
        "valid": True,
        "reason": "block_range_valid",
        "startBlockId": start_block_id,
        "endBlockId": end_block_id,
        "rangeLength": range_length,
    }


def blocks_to_prompt_text(
    blocks: list[HtmlBlock], max_blocks: int = MAX_PROMPT_BLOCKS
) -> str:
    """Convert blocks to a text representation for LLM prompts."""
    lines = []
    for b in blocks[:max_blocks]:
        section_info = f" [Section: {b.section_title}]" if b.section_title else ""
        lines.append(f"[{b.block_id}]{section_info} ({b.tag}): {b.text}")
    return "\n\n".join(lines)


def _parse_arxiv_html_document(
    html: str,
    *,
    exclude_back_matter: bool,
) -> tuple[list[HtmlBlock], BeautifulSoup]:
    soup = BeautifulSoup(html, "lxml")
    body = (
        soup.find("article", class_="ltx_document")
        or soup.find("article")
        or soup.find("body")
        or soup
    )
    blocks: list[HtmlBlock] = []
    current_section = ""
    in_back_matter = False

    for element in body.descendants:
        if not isinstance(element, Tag):
            continue
        if not _is_addressable_block(element):
            continue

        text = _normalize_text(element.get_text(" ", strip=True))
        if not text or len(text) < 10:
            continue

        if element.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            current_section = text
            if _is_back_matter_heading(text):
                in_back_matter = True

        if exclude_back_matter and in_back_matter:
            continue

        block_id = _canonical_block_id(len(blocks))
        existing_id = element.get("id", "")
        html_anchor = f"#{existing_id}" if existing_id else ""
        element["data-paper-block-id"] = block_id

        blocks.append(
            HtmlBlock(
                block_id=block_id,
                order_index=len(blocks),
                tag=element.name,
                text=text,
                section_title=current_section,
                html_anchor=html_anchor,
            )
        )

    return blocks, soup


def _invalid_range(
    reason: str,
    citation: dict,
    available_block_count: int,
    *,
    start_block: HtmlBlock | None = None,
    end_block: HtmlBlock | None = None,
    **extra: object,
) -> dict:
    details = {
        "valid": False,
        "reason": reason,
        "startBlockId": citation.get("startBlockId", ""),
        "endBlockId": citation.get("endBlockId", ""),
        "sectionTitle": _preview(citation.get("sectionTitle", "")),
        "availableBlockCount": available_block_count,
        **extra,
    }
    if start_block:
        details["startBlockPreview"] = _block_preview(start_block)
    if end_block:
        details["endBlockPreview"] = _block_preview(end_block)
    return details


def _block_preview(block: HtmlBlock) -> dict:
    return {
        "blockId": block.block_id,
        "orderIndex": block.order_index,
        "htmlAnchor": block.html_anchor,
        "tag": block.tag,
        "sectionTitle": _preview(block.section_title),
        "text": _preview(block.text),
    }


def _canonical_block_id(order_index: int) -> str:
    return f"B{order_index:03d}"


def _is_addressable_block(element: Tag) -> bool:
    if element.name in ALWAYS_ADDRESSABLE_TAGS:
        return True
    if element.name != "li":
        return False
    return not _has_addressable_block_descendant(element)


def _has_addressable_block_descendant(element: Tag) -> bool:
    return any(
        isinstance(descendant, Tag) and descendant.name in CONTENT_TAGS
        for descendant in element.descendants
    )


def _is_back_matter_heading(text: str) -> bool:
    return bool(BACK_MATTER_RE.search(text))


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _preview(value: object, limit: int = 400) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."
