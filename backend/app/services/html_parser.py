"""Parse arXiv HTML into addressable blocks for idea map generation."""

import hashlib
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Tag


@dataclass
class HtmlBlock:
    block_id: str
    tag: str
    text: str
    section_title: str = ""
    html_anchor: str = ""


def parse_arxiv_html(html: str) -> list[HtmlBlock]:
    """Parse arXiv HTML into addressable blocks preserving section titles."""
    soup = BeautifulSoup(html, "lxml")

    body = soup.find("body") or soup
    blocks: list[HtmlBlock] = []
    current_section = ""
    block_counter = 0

    content_tags = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "td", "th", "figcaption", "blockquote"}

    for element in body.descendants:
        if not isinstance(element, Tag):
            continue
        if element.name not in content_tags:
            continue

        text = element.get_text(strip=True)
        if not text or len(text) < 10:
            continue

        if element.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            current_section = text

        existing_id = element.get("id", "")
        if existing_id:
            anchor = str(existing_id)
        else:
            anchor = f"block-{block_counter}"
            element["id"] = anchor

        block_id = anchor
        block_counter += 1

        blocks.append(HtmlBlock(
            block_id=block_id,
            tag=element.name,
            text=text,
            section_title=current_section,
            html_anchor=f"#{anchor}",
        ))

    return blocks


def validate_citation(blocks: list[HtmlBlock], citation: dict) -> bool:
    """Validate a warrant citation against parsed blocks."""
    block_id = citation.get("blockId", "")
    quote = citation.get("quote", "")
    prefix = citation.get("prefix", "")
    suffix = citation.get("suffix", "")

    block_map = {b.block_id: b for b in blocks}
    block = block_map.get(block_id)
    if not block:
        return False

    if quote and quote in block.text:
        return True

    if prefix and suffix:
        if prefix in block.text and suffix in block.text:
            p_idx = block.text.find(prefix)
            s_idx = block.text.find(suffix)
            if p_idx < s_idx:
                return True

    return False


def blocks_to_prompt_text(blocks: list[HtmlBlock], max_blocks: int = 200) -> str:
    """Convert blocks to a text representation for LLM prompts."""
    lines = []
    for b in blocks[:max_blocks]:
        section_info = f" [Section: {b.section_title}]" if b.section_title else ""
        lines.append(f"[{b.block_id}]{section_info} ({b.tag}): {b.text}")
    return "\n\n".join(lines)
