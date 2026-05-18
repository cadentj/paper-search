"""Shared arXiv metadata helpers for standalone scripts."""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from typing import Any

import httpx

ARXIV_API_URL = "https://export.arxiv.org/api/query"
ATOM_NS = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"
VERSION_RE = re.compile(r"v\d+$")


def normalize_arxiv_id(value: str) -> str:
    arxiv_id = value.rstrip("/").rsplit("/", 1)[-1]
    return VERSION_RE.sub("", arxiv_id)


def parse_arxiv_feed(xml_text: str) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    papers: list[dict[str, Any]] = []

    for entry in root.findall(f"{ATOM_NS}entry"):
        id_el = entry.find(f"{ATOM_NS}id")
        title_el = entry.find(f"{ATOM_NS}title")
        summary_el = entry.find(f"{ATOM_NS}summary")

        if id_el is None or not id_el.text:
            continue

        arxiv_id = normalize_arxiv_id(id_el.text)
        authors = [
            name_el.text.strip()
            for author_el in entry.findall(f"{ATOM_NS}author")
            for name_el in [author_el.find(f"{ATOM_NS}name")]
            if name_el is not None and name_el.text
        ]
        categories = [
            category_el.attrib["term"]
            for category_el in entry.findall(f"{ATOM_NS}category")
            if category_el.attrib.get("term")
        ]
        primary_category_el = entry.find(f"{ARXIV_NS}primary_category")
        primary_category = (
            primary_category_el.attrib.get("term")
            if primary_category_el is not None
            else None
        )
        if primary_category and primary_category not in categories:
            categories.insert(0, primary_category)

        papers.append(
            {
                "arxiv_id": arxiv_id,
                "title": " ".join((title_el.text or "").split()) if title_el is not None else "",
                "abstract": " ".join((summary_el.text or "").split()) if summary_el is not None else "",
                "authors": authors,
                "categories": categories,
            }
        )

    return papers


def fetch_metadata_by_ids(
    arxiv_ids: list[str],
    *,
    client: httpx.Client,
    batch_size: int = 100,
    batch_delay_seconds: float = 3.0,
) -> dict[str, dict[str, Any]]:
    normalized_ids = [normalize_arxiv_id(arxiv_id) for arxiv_id in arxiv_ids if arxiv_id]
    unique_ids = list(dict.fromkeys(normalized_ids))
    if not unique_ids:
        return {}

    metadata_by_id: dict[str, dict[str, Any]] = {}
    for start in range(0, len(unique_ids), batch_size):
        batch = unique_ids[start : start + batch_size]
        response = client.get(ARXIV_API_URL, params={"id_list": ",".join(batch)})
        response.raise_for_status()
        for paper in parse_arxiv_feed(response.text):
            metadata_by_id[paper["arxiv_id"]] = paper
        if start + batch_size < len(unique_ids) and batch_delay_seconds > 0:
            time.sleep(batch_delay_seconds)

    return metadata_by_id
