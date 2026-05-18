"""Parse arXiv HTML into addressable blocks for idea map generation."""

from dataclasses import dataclass

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
    return citation_validation_diagnostics(blocks, citation)["valid"]


def citation_validation_diagnostics(blocks: list[HtmlBlock], citation: dict) -> dict:
    """Return validation status plus concise diagnostics for logging."""
    block_id = citation.get("blockId", "")
    quote = citation.get("quote", "")
    prefix = citation.get("prefix", "")
    suffix = citation.get("suffix", "")

    block_map = {b.block_id: b for b in blocks}
    block = block_map.get(block_id)
    if not block:
        return {
            "valid": False,
            "reason": "block_id_not_found" if block_id else "missing_block_id",
            "blockId": block_id,
            "quote": _preview(quote),
            "prefix": _preview(prefix),
            "suffix": _preview(suffix),
            "htmlAnchor": citation.get("htmlAnchor", ""),
            "availableBlockCount": len(blocks),
        }

    if quote and quote in block.text:
        return {
            "valid": True,
            "reason": "quote_exact_match",
            "blockId": block_id,
        }

    if prefix and suffix:
        if prefix in block.text and suffix in block.text:
            p_idx = block.text.find(prefix)
            s_idx = block.text.find(suffix)
            if p_idx < s_idx:
                return {
                    "valid": True,
                    "reason": "prefix_suffix_ordered_match",
                    "blockId": block_id,
                }

    return {
        "valid": False,
        "reason": _citation_failure_reason(block.text, quote, prefix, suffix),
        "blockId": block_id,
        "quote": _preview(quote),
        "prefix": _preview(prefix),
        "suffix": _preview(suffix),
        "htmlAnchor": citation.get("htmlAnchor", ""),
        "blockTag": block.tag,
        "blockSectionTitle": _preview(block.section_title),
        "blockTextPreview": _preview(block.text),
    }


def _citation_failure_reason(block_text: str, quote: str, prefix: str, suffix: str) -> str:
    if quote:
        return "quote_not_found_in_block"
    if prefix or suffix:
        if not prefix:
            return "missing_prefix"
        if not suffix:
            return "missing_suffix"
        if prefix not in block_text and suffix not in block_text:
            return "prefix_and_suffix_not_found_in_block"
        if prefix not in block_text:
            return "prefix_not_found_in_block"
        if suffix not in block_text:
            return "suffix_not_found_in_block"
        return "prefix_not_before_suffix"
    return "missing_quote_or_prefix_suffix"


def _preview(value: object, limit: int = 400) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def blocks_to_prompt_text(blocks: list[HtmlBlock], max_blocks: int = 200) -> str:
    """Convert blocks to a text representation for LLM prompts."""
    lines = []
    for b in blocks[:max_blocks]:
        section_info = f" [Section: {b.section_title}]" if b.section_title else ""
        lines.append(f"[{b.block_id}]{section_info} ({b.tag}): {b.text}")
    return "\n\n".join(lines)
