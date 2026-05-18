"""Parse arXiv HTML metadata and fetch it from R2 (API or public URL)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from threading import Lock
from typing import Any, Callable

import httpx
from bs4 import BeautifulSoup
from botocore.exceptions import ClientError
from tqdm import tqdm

from arxiv_metadata import normalize_arxiv_id

# arXiv HTML puts title, authors, and abstract near the top of the file.
DEFAULT_HTML_HEAD_BYTES = 262_144


@dataclass
class _FetchStats:
    head_ok: int = 0
    full_fetch: int = 0
    missing: int = 0

    def merge(self, other: "_FetchStats") -> None:
        with _fetch_stats_lock:
            self.head_ok += other.head_ok
            self.full_fetch += other.full_fetch
            self.missing += other.missing


_fetch_stats = _FetchStats()
_fetch_stats_lock = Lock()


def html_key_for_arxiv_id(arxiv_id: str) -> str:
    return f"data/{arxiv_id[:4]}/{arxiv_id}.html"


def public_html_url(public_base_url: str, html_key: str) -> str:
    from urllib.parse import quote, urljoin

    base = public_base_url.rstrip("/") + "/"
    path = html_key.lstrip("/")
    return urljoin(base, quote(path, safe="/:.-_"))


def extract_html_metadata(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    title_el = soup.select_one(".ltx_title_document") or soup.find("title")
    authors = [
        _normalize_text(author.get_text(" ", strip=True))
        for author in soup.select(".ltx_authors .ltx_personname")
    ]
    abstract_el = soup.select_one(".ltx_abstract")
    if abstract_el:
        for heading in abstract_el.select(".ltx_title_abstract"):
            heading.decompose()
        abstract = _normalize_text(abstract_el.get_text(" ", strip=True))
    else:
        abstract = ""

    return {
        "title": _normalize_text(title_el.get_text(" ", strip=True)) if title_el else "",
        "abstract": abstract,
        "authors": [author for author in authors if author],
    }


def fetch_metadata_from_r2(
    papers: list[dict[str, str]],
    *,
    client: Any,
    bucket: str,
    workers: int = 16,
    html_head_bytes: int = DEFAULT_HTML_HEAD_BYTES,
) -> dict[str, dict[str, Any]]:
    if not papers:
        return {}
    if not bucket:
        raise ValueError("R2 bucket must be set")

    global _fetch_stats
    _fetch_stats = _FetchStats()

    def load_html(paper: dict[str, str]) -> str | None:
        arxiv_id = normalize_arxiv_id(paper.get("arxiv_id") or "")
        html_key = paper.get("html_key") or html_key_for_arxiv_id(arxiv_id)
        return _fetch_html_head_or_full_from_r2(
            client,
            bucket=bucket,
            html_key=html_key,
            head_bytes=html_head_bytes,
        )

    return _fetch_metadata_parallel(
        papers,
        workers=workers,
        desc="fetching HTML metadata (R2 API)",
        load_html=load_html,
    )


def fetch_metadata_from_public_html(
    papers: list[dict[str, str]],
    *,
    public_base_url: str,
    workers: int = 16,
    html_head_bytes: int = DEFAULT_HTML_HEAD_BYTES,
) -> dict[str, dict[str, Any]]:
    if not papers:
        return {}
    if not public_base_url.strip():
        raise ValueError("ARXIV_HTML_PUBLIC_BASE_URL must be set")

    worker_count = max(workers, 1)

    def load_html(paper: dict[str, str]) -> str | None:
        arxiv_id = normalize_arxiv_id(paper.get("arxiv_id") or "")
        html_key = paper.get("html_key") or html_key_for_arxiv_id(arxiv_id)
        url = public_html_url(public_base_url, html_key)
        return _fetch_html_head_or_full_from_url(
            http_client,
            url=url,
            head_bytes=html_head_bytes,
        )

    with httpx.Client(
        timeout=30.0,
        follow_redirects=True,
        limits=httpx.Limits(
            max_connections=max(worker_count * 2, 16),
            max_keepalive_connections=worker_count,
        ),
    ) as http_client:
        return _fetch_metadata_parallel(
            papers,
            workers=worker_count,
            desc="fetching HTML metadata (public URL)",
            load_html=load_html,
        )


def _fetch_metadata_parallel(
    papers: list[dict[str, str]],
    *,
    workers: int,
    desc: str,
    load_html: Callable[[dict[str, str]], str | None],
) -> dict[str, dict[str, Any]]:
    metadata_by_id: dict[str, dict[str, Any]] = {}
    worker_count = max(workers, 1)
    parsed = 0
    failed = 0

    with ThreadPoolExecutor(max_workers=worker_count) as executor, tqdm(
        total=len(papers),
        desc=desc,
        unit="paper",
        dynamic_ncols=True,
    ) as progress:
        futures = {
            executor.submit(_metadata_for_paper, paper, load_html): paper["arxiv_id"]
            for paper in papers
        }
        for future in as_completed(futures):
            metadata = future.result()
            if metadata:
                metadata_by_id[metadata["arxiv_id"]] = metadata
                parsed += 1
            else:
                failed += 1
            progress.update(1)
            progress.set_postfix(
                parsed=parsed,
                failed=failed,
                head=_fetch_stats.head_ok,
                full=_fetch_stats.full_fetch,
                refresh=False,
            )

    return metadata_by_id


def _metadata_for_paper(
    paper: dict[str, str],
    load_html: Callable[[dict[str, str]], str | None],
) -> dict[str, Any] | None:
    arxiv_id = normalize_arxiv_id(paper.get("arxiv_id") or "")
    html = load_html(paper)
    if not html:
        return None

    metadata = extract_html_metadata(html)
    if not metadata.get("abstract"):
        return None

    return {
        "arxiv_id": arxiv_id,
        "title": metadata["title"],
        "abstract": metadata["abstract"],
        "authors": metadata["authors"],
    }


def _fetch_html_head_or_full_from_r2(
    client: Any,
    *,
    bucket: str,
    html_key: str,
    head_bytes: int,
) -> str | None:
    stats = _FetchStats()
    if head_bytes > 0:
        head = _fetch_html_from_r2(
            client,
            bucket=bucket,
            html_key=html_key,
            byte_end=head_bytes - 1,
        )
        if head:
            if extract_html_metadata(head).get("abstract"):
                stats.head_ok = 1
                _fetch_stats.merge(stats)
                return head
            full = _fetch_html_from_r2(client, bucket=bucket, html_key=html_key)
            if full:
                stats.full_fetch = 1
            else:
                stats.missing = 1
            _fetch_stats.merge(stats)
            return full

    full = _fetch_html_from_r2(client, bucket=bucket, html_key=html_key)
    if full:
        stats.full_fetch = 1
    else:
        stats.missing = 1
    _fetch_stats.merge(stats)
    return full


def _fetch_html_head_or_full_from_url(
    client: httpx.Client,
    *,
    url: str,
    head_bytes: int,
) -> str | None:
    if head_bytes > 0:
        head = _fetch_html_from_url(client, url=url, byte_end=head_bytes - 1)
        if head and extract_html_metadata(head).get("abstract"):
            return head

    return _fetch_html_from_url(client, url=url)


def _fetch_html_from_r2(
    client: Any,
    *,
    bucket: str,
    html_key: str,
    byte_end: int | None = None,
) -> str | None:
    params: dict[str, Any] = {"Bucket": bucket, "Key": html_key}
    if byte_end is not None:
        params["Range"] = f"bytes=0-{byte_end}"

    try:
        response = client.get_object(**params)
        return response["Body"].read().decode("utf-8", errors="replace")
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")
        status_code = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if status_code in {403, 404} or error_code in {
            "403",
            "404",
            "NoSuchKey",
            "NotFound",
            "Forbidden",
            "AccessDenied",
        }:
            return None
        raise


def _fetch_html_from_url(
    client: httpx.Client,
    *,
    url: str,
    byte_end: int | None = None,
) -> str | None:
    headers = {}
    if byte_end is not None:
        headers["Range"] = f"bytes=0-{byte_end}"

    try:
        response = client.get(url, headers=headers)
        response.raise_for_status()
    except httpx.HTTPError:
        return None

    return response.text


def _normalize_text(value: str) -> str:
    return " ".join(value.split())
