#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27.0"]
# ///
"""Polite, resumable arXiv HTML scraper for recent category papers."""

from __future__ import annotations

import argparse
import json
import random
import re
import sqlite3
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Iterable

import httpx


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "arxiv_html_cache"
ARXIV_API_URL = "https://export.arxiv.org/api/query"
ATOM_NS = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"
VERSION_RE = re.compile(r"v\d+$")
SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_.-]+")


@dataclass(frozen=True)
class Candidate:
    arxiv_id: str
    version: str
    title: str
    categories: list[str]
    latest_version_date: str

    @property
    def html_url(self) -> str:
        return f"https://arxiv.org/html/{self.arxiv_id}"


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    db_path = output_dir / "scrape_state.sqlite"

    anchor_date = parse_anchor_date(args.anchor_date)
    start_date = anchor_date - timedelta(days=args.days - 1)
    categories = set(args.categories)

    candidates = load_candidates(args, categories, start_date, anchor_date)
    if args.shuffle:
        random.shuffle(candidates)
    print(
        f"Loaded {len(candidates)} candidates for "
        f"{start_date.isoformat()}..{anchor_date.isoformat()} categories={sorted(categories)}",
        flush=True,
    )

    with connect_state(db_path) as conn:
        create_state(conn)
        upsert_candidates(conn, candidates)

    if args.mode == "benchmark":
        run_benchmark(args, candidates, output_dir, db_path)
        return

    if args.mode == "auto":
        result = run_benchmark(args, candidates, output_dir, db_path)
        strategy = result["recommended_strategy"]
    else:
        strategy = args.strategy

    run_scrape(args, candidates, output_dir, db_path, strategy=strategy)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["benchmark", "run", "auto"], default="benchmark")
    parser.add_argument("--strategy", choices=["steady", "burst"], default="steady")
    parser.add_argument("--metadata-path", help="Optional Kaggle arXiv metadata JSONL path.")
    parser.add_argument("--ids-file", help="Optional newline-delimited arXiv IDs or JSONL records.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--anchor-date", help="YYYY-MM-DD. Defaults to today UTC.")
    parser.add_argument("--categories", nargs="+", default=["cs.AI", "cs.CL", "cs.LG"])
    parser.add_argument("--limit", type=int, default=None, help="Limit candidate count after filtering.")
    parser.add_argument("--shuffle", action="store_true", help="Shuffle candidates before fetching.")
    parser.add_argument("--steady-rps", type=float, default=2.0)
    parser.add_argument("--burst-size", type=int, default=4)
    parser.add_argument("--burst-sleep", type=float, default=2.0)
    parser.add_argument("--benchmark-seconds", type=int, default=180)
    parser.add_argument("--max-runtime-hours", type=float, default=None)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--user-agent", default="paper-search/0.1 contact: local-research")
    return parser.parse_args()


def parse_anchor_date(value: str | None) -> date:
    if value:
        return date.fromisoformat(value)
    return datetime.now(timezone.utc).date()


def load_candidates(
    args: argparse.Namespace,
    categories: set[str],
    start_date: date,
    anchor_date: date,
) -> list[Candidate]:
    if args.ids_file:
        candidates = candidates_from_ids_file(Path(args.ids_file), categories, anchor_date)
    elif args.metadata_path:
        candidates = candidates_from_kaggle_metadata(
            Path(args.metadata_path), categories, start_date, anchor_date
        )
    else:
        candidates = candidates_from_arxiv_api(categories, start_date, anchor_date)

    deduped = list({candidate.arxiv_id: candidate for candidate in candidates}.values())
    deduped.sort(key=lambda item: (item.latest_version_date, item.arxiv_id))
    if args.limit is not None:
        return deduped[: args.limit]
    return deduped


def candidates_from_ids_file(
    path: Path,
    categories: set[str],
    anchor_date: date,
) -> list[Candidate]:
    candidates = []
    with path.expanduser().open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            if line.lstrip().startswith("{"):
                record = json.loads(line)
                arxiv_id = normalize_arxiv_id(record["arxiv_id"] if "arxiv_id" in record else record["id"])
                record_categories = record.get("categories", sorted(categories))
                candidates.append(
                    Candidate(
                        arxiv_id=arxiv_id,
                        version=record.get("version", ""),
                        title=record.get("title", ""),
                        categories=list(record_categories),
                        latest_version_date=record.get("latest_version_date", anchor_date.isoformat()),
                    )
                )
            else:
                arxiv_id = normalize_arxiv_id(line.strip())
                candidates.append(
                    Candidate(
                        arxiv_id=arxiv_id,
                        version="",
                        title="",
                        categories=sorted(categories),
                        latest_version_date=anchor_date.isoformat(),
                    )
                )
    return candidates


def candidates_from_kaggle_metadata(
    path: Path,
    categories: set[str],
    start_date: date,
    anchor_date: date,
) -> list[Candidate]:
    candidates = []
    with path.expanduser().open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            record_categories = (record.get("categories") or "").split()
            if not categories.intersection(record_categories):
                continue
            latest_version = (record.get("versions") or [{}])[-1]
            latest_date = parse_arxiv_email_date(latest_version.get("created"))
            if not latest_date:
                continue
            if latest_date.date() < start_date or latest_date.date() > anchor_date:
                continue
            candidates.append(
                Candidate(
                    arxiv_id=normalize_arxiv_id(record.get("id", "")),
                    version=latest_version.get("version", ""),
                    title=" ".join((record.get("title") or "").split()),
                    categories=record_categories,
                    latest_version_date=latest_date.isoformat(),
                )
            )
    return candidates


def candidates_from_arxiv_api(
    categories: set[str],
    start_date: date,
    anchor_date: date,
) -> list[Candidate]:
    query = (
        "(" + " OR ".join(f"cat:{category}" for category in sorted(categories)) + ")"
        f" AND submittedDate:[{start_date:%Y%m%d}0000 TO {anchor_date:%Y%m%d}2359]"
    )
    candidates = []
    start = 0
    page_size = 100
    while True:
        params = {
            "search_query": query,
            "start": start,
            "max_results": page_size,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            response = client.get(ARXIV_API_URL, params=params)
            response.raise_for_status()
        page = parse_arxiv_feed(response.text)
        if not page:
            break
        candidates.extend(page)
        if len(page) < page_size:
            break
        start += page_size
        time.sleep(3.0)
    return candidates


def parse_arxiv_feed(xml_text: str) -> list[Candidate]:
    root = ET.fromstring(xml_text)
    candidates = []
    for entry in root.findall(f"{ATOM_NS}entry"):
        id_el = entry.find(f"{ATOM_NS}id")
        title_el = entry.find(f"{ATOM_NS}title")
        updated_el = entry.find(f"{ATOM_NS}updated")
        if id_el is None or not id_el.text:
            continue
        categories = [
            category_el.attrib["term"]
            for category_el in entry.findall(f"{ATOM_NS}category")
            if category_el.attrib.get("term")
        ]
        primary_el = entry.find(f"{ARXIV_NS}primary_category")
        primary = primary_el.attrib.get("term") if primary_el is not None else None
        if primary and primary not in categories:
            categories.insert(0, primary)
        candidates.append(
            Candidate(
                arxiv_id=normalize_arxiv_id(id_el.text),
                version=version_from_id(id_el.text),
                title=" ".join((title_el.text or "").split()) if title_el is not None else "",
                categories=categories,
                latest_version_date=updated_el.text if updated_el is not None else "",
            )
        )
    return candidates


def run_benchmark(
    args: argparse.Namespace,
    candidates: list[Candidate],
    output_dir: Path,
    db_path: Path,
) -> dict[str, Any]:
    sample = candidates.copy()
    random.shuffle(sample)
    results = {}
    for strategy in ("burst", "steady"):
        print(f"Benchmarking {strategy} for {args.benchmark_seconds}s", flush=True)
        results[strategy] = run_scrape(
            args,
            sample,
            output_dir,
            db_path,
            strategy=strategy,
            max_seconds=args.benchmark_seconds,
            benchmark=True,
        )

    recommended = max(results, key=lambda key: results[key]["successes_per_minute"])
    payload = {
        "at": datetime.now(timezone.utc).isoformat(),
        "recommended_strategy": recommended,
        "results": results,
    }
    report_path = output_dir / "benchmark_results.json"
    report_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Benchmark complete. Recommended strategy: {recommended}. Report: {report_path}", flush=True)
    return payload


def run_scrape(
    args: argparse.Namespace,
    candidates: list[Candidate],
    output_dir: Path,
    db_path: Path,
    *,
    strategy: str,
    max_seconds: int | None = None,
    benchmark: bool = False,
) -> dict[str, Any]:
    started = time.monotonic()
    deadline = started + max_seconds if max_seconds else None
    if args.max_runtime_hours and not benchmark:
        deadline = started + args.max_runtime_hours * 3600

    headers = {"User-Agent": args.user_agent}
    stats = {"attempted": 0, "success": 0, "missing": 0, "error": 0, "bytes": 0}
    burst_counter = 0
    with connect_state(db_path) as conn, httpx.Client(
        timeout=args.timeout,
        follow_redirects=True,
        headers=headers,
    ) as client:
        create_state(conn)
        for candidate in candidates:
            if deadline and time.monotonic() >= deadline:
                break
            if already_done(conn, candidate.arxiv_id):
                continue

            wait_for_strategy(strategy, args, burst_counter)
            burst_counter += 1

            stats["attempted"] += 1
            result = fetch_one(client, candidate, output_dir)
            stats[result["status"]] += 1
            stats["bytes"] += result.get("bytes", 0)
            record_result(conn, candidate, result)
            print(
                f"{candidate.arxiv_id} {result['status']} "
                f"{result.get('status_code', '')} {result.get('bytes', 0)}B",
                flush=True,
            )

    elapsed = max(time.monotonic() - started, 0.001)
    return {
        **stats,
        "elapsed_seconds": elapsed,
        "successes_per_minute": stats["success"] / elapsed * 60.0,
        "strategy": strategy,
    }


def fetch_one(client: httpx.Client, candidate: Candidate, output_dir: Path) -> dict[str, Any]:
    try:
        response = client.get(candidate.html_url)
    except httpx.HTTPError as exc:
        return {"status": "error", "error": str(exc)}

    if response.status_code == 404:
        return {"status": "missing", "status_code": response.status_code}
    if response.status_code in {403, 429, 500, 502, 503, 504}:
        retry_after = response.headers.get("retry-after")
        if retry_after and retry_after.isdigit():
            time.sleep(float(retry_after))
        return {"status": "error", "status_code": response.status_code}
    if response.status_code != 200:
        return {"status": "error", "status_code": response.status_code}

    html_dir = output_dir / "html" / candidate.arxiv_id[:4]
    html_dir.mkdir(parents=True, exist_ok=True)
    html_path = html_dir / f"{safe_filename(candidate.arxiv_id)}.html"
    html_path.write_text(response.text, encoding=response.encoding or "utf-8")
    return {
        "status": "success",
        "status_code": response.status_code,
        "bytes": len(response.content),
        "html_path": str(html_path),
        "source_url": str(response.url),
    }


def wait_for_strategy(strategy: str, args: argparse.Namespace, burst_counter: int) -> None:
    if strategy == "steady":
        time.sleep(max(0.0, 1.0 / args.steady_rps))
        return
    if burst_counter > 0 and burst_counter % args.burst_size == 0:
        time.sleep(args.burst_sleep)


def connect_state(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(db_path)


def create_state(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS arxiv_html_scrape (
            arxiv_id TEXT PRIMARY KEY,
            version TEXT,
            title TEXT NOT NULL DEFAULT '',
            categories TEXT NOT NULL DEFAULT '[]',
            latest_version_date TEXT,
            source_url TEXT,
            html_path TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            status_code INTEGER,
            bytes INTEGER NOT NULL DEFAULT 0,
            error TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


def upsert_candidates(conn: sqlite3.Connection, candidates: Iterable[Candidate]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    for candidate in candidates:
        conn.execute(
            """
            INSERT INTO arxiv_html_scrape (
                arxiv_id, version, title, categories, latest_version_date, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(arxiv_id) DO UPDATE SET
                version = excluded.version,
                title = excluded.title,
                categories = excluded.categories,
                latest_version_date = excluded.latest_version_date
            """,
            (
                candidate.arxiv_id,
                candidate.version,
                candidate.title,
                json.dumps(candidate.categories),
                candidate.latest_version_date,
                now,
            ),
        )
    conn.commit()


def already_done(conn: sqlite3.Connection, arxiv_id: str) -> bool:
    row = conn.execute(
        "SELECT status FROM arxiv_html_scrape WHERE arxiv_id = ?",
        (arxiv_id,),
    ).fetchone()
    return bool(row and row[0] == "success")


def record_result(conn: sqlite3.Connection, candidate: Candidate, result: dict[str, Any]) -> None:
    conn.execute(
        """
        UPDATE arxiv_html_scrape SET
            source_url = ?,
            html_path = ?,
            status = ?,
            status_code = ?,
            bytes = ?,
            error = ?,
            updated_at = ?
        WHERE arxiv_id = ?
        """,
        (
            result.get("source_url") or candidate.html_url,
            result.get("html_path"),
            result["status"],
            result.get("status_code"),
            result.get("bytes", 0),
            result.get("error"),
            datetime.now(timezone.utc).isoformat(),
            candidate.arxiv_id,
        ),
    )
    conn.commit()


def parse_arxiv_email_date(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = parsedate_to_datetime(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_arxiv_id(value: str) -> str:
    arxiv_id = value.rstrip("/").rsplit("/", 1)[-1]
    return VERSION_RE.sub("", arxiv_id)


def version_from_id(value: str) -> str:
    arxiv_id = value.rstrip("/").rsplit("/", 1)[-1]
    match = VERSION_RE.search(arxiv_id)
    return match.group(0) if match else ""


def safe_filename(arxiv_id: str) -> str:
    return SAFE_ID_RE.sub("_", arxiv_id)


if __name__ == "__main__":
    main()
