"""Resolve public R2 arXiv HTML documents."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.public_arxiv_cache import fetch_public_paper_html


VERSION_RE = re.compile(r"v\d+$")


@dataclass(frozen=True)
class PaperHtmlDocument:
    arxiv_id: str
    source_url: str
    html: str


def arxiv_html_url(arxiv_id: str) -> str:
    return f"https://arxiv.org/html/{normalize_arxiv_id(arxiv_id)}"


def read_paper_html(
    arxiv_id: str | None,
    *,
    html_url: str | None = None,
) -> PaperHtmlDocument | None:
    remote_html = fetch_public_paper_html(arxiv_id=arxiv_id, html_url=html_url)
    if not remote_html:
        return None

    return PaperHtmlDocument(
        arxiv_id=normalize_arxiv_id(arxiv_id or ""),
        source_url=remote_html["source_url"],
        html=remote_html["html"],
    )


def normalize_arxiv_id(value: str) -> str:
    arxiv_id = value.rstrip("/").rsplit("/", 1)[-1]
    return VERSION_RE.sub("", arxiv_id)
