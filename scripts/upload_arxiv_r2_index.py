#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["beautifulsoup4>=4.12.0", "boto3>=1.34.0", "lxml>=5.0.0"]
# ///
"""Build and upload a sharded arXiv HTML scrape index to Cloudflare R2."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from arxiv_html_metadata import extract_html_metadata
from arxiv_index import (
    DEFAULT_DATE_INDEX_PREFIX,
    DEFAULT_HTML_PREFIX,
    DEFAULT_INDEX_KEY,
    build_sharded_index_from_daily_papers,
    json_body,
    upload_sharded_index,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATE_DB = REPO_ROOT / "data" / "arxiv_html_cache" / "scrape_state.sqlite"
DEFAULT_CACHE_DIR = REPO_ROOT / "data" / "arxiv_html_cache" / "html"


@dataclass(frozen=True)
class ScrapedPaper:
    arxiv_id: str
    version: str
    title: str
    categories: list[str]
    latest_version_date: str
    source_url: str
    html_key: str
    bytes: int


def main() -> None:
    args = parse_args()
    state_db = Path(args.state_db).expanduser().resolve()
    cache_dir = Path(args.cache_dir).expanduser().resolve()

    manifest, date_shards = build_index(
        state_db=state_db,
        cache_dir=cache_dir,
        prefix=args.prefix,
        date_index_prefix=args.date_index_prefix,
        verify_files=not args.no_verify_files,
    )

    if args.output_dir:
        write_local_output(Path(args.output_dir).expanduser().resolve(), manifest, date_shards, pretty=args.pretty)

    print_summary(manifest)

    if args.dry_run:
        return

    client = r2_client(args)
    upload_sharded_index(
        client,
        bucket=args.bucket,
        index_key=args.index_key,
        manifest=manifest,
        date_shards=date_shards,
        pretty=args.pretty,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", default=os.environ.get("R2_ACCOUNT_ID"))
    parser.add_argument("--access-key-id", default=os.environ.get("R2_ACCESS_KEY_ID"))
    parser.add_argument("--secret-access-key", default=os.environ.get("R2_SECRET_ACCESS_KEY"))
    parser.add_argument("--bucket", default=os.environ.get("R2_BUCKET"))
    parser.add_argument("--state-db", default=str(DEFAULT_STATE_DB))
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--prefix", default=DEFAULT_HTML_PREFIX)
    parser.add_argument("--index-key", default=os.environ.get("ARXIV_HTML_INDEX_PATH", DEFAULT_INDEX_KEY))
    parser.add_argument("--date-index-prefix", default=DEFAULT_DATE_INDEX_PREFIX)
    parser.add_argument("--output-dir", help="Optional local directory to write manifest and date shards.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument(
        "--no-verify-files",
        action="store_true",
        help="Do not require each HTML file to exist under --cache-dir.",
    )
    return parser.parse_args()


def build_index(
    *,
    state_db: Path,
    cache_dir: Path,
    prefix: str,
    date_index_prefix: str,
    verify_files: bool,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    if not state_db.exists():
        raise SystemExit(f"State DB not found: {state_db}")
    if verify_files and not cache_dir.exists():
        raise SystemExit(f"Cache dir not found: {cache_dir}")

    rows = load_success_rows(state_db)
    daily_papers: dict[str, list[dict[str, Any]]] = {}
    skipped_missing = 0

    for row in rows:
        paper = paper_from_row(
            row,
            cache_dir=cache_dir,
            prefix=prefix,
            verify_files=verify_files,
        )
        if not paper:
            skipped_missing += 1
            continue

        day = date_part(paper.latest_version_date)
        if not day:
            continue

        metadata = metadata_from_local_html(
            html_path=resolve_html_path(
                arxiv_id=paper.arxiv_id,
                recorded_path=row["html_path"],
                cache_dir=cache_dir,
                verify_files=verify_files,
            ),
        )
        daily_papers.setdefault(day, []).append(
            {
                "arxiv_id": paper.arxiv_id,
                "version": paper.version,
                "title": metadata["title"] or paper.title,
                "abstract": metadata["abstract"],
                "authors": metadata["authors"],
                "categories": paper.categories,
                "latest_version_date": paper.latest_version_date,
                "source_url": paper.source_url,
                "html_key": paper.html_key,
                "bytes": paper.bytes,
            }
        )

    manifest, date_shards = build_sharded_index_from_daily_papers(
        daily_papers,
        html_prefix=prefix,
        date_index_prefix=date_index_prefix,
        skipped_missing_files=skipped_missing,
    )
    return manifest, date_shards


def write_local_output(
    output_dir: Path,
    manifest: dict[str, Any],
    date_shards: dict[str, dict[str, Any]],
    *,
    pretty: bool,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "papers-by-date.json").write_text(json_body(manifest, pretty=pretty), encoding="utf-8")
    dates_dir = output_dir / "dates"
    dates_dir.mkdir(parents=True, exist_ok=True)
    for day, shard in date_shards.items():
        (dates_dir / f"{day}.json").write_text(json_body(shard, pretty=pretty), encoding="utf-8")
    print(f"Wrote manifest and {len(date_shards)} date shards to {output_dir}")


def load_success_rows(state_db: Path) -> list[sqlite3.Row]:
    with sqlite3.connect(state_db) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            """
            SELECT arxiv_id, version, title, categories, latest_version_date,
                   source_url, html_path, bytes
            FROM arxiv_html_scrape
            WHERE status = 'success'
            ORDER BY latest_version_date DESC, arxiv_id ASC
            """
        ).fetchall()


def paper_from_row(
    row: sqlite3.Row,
    *,
    cache_dir: Path,
    prefix: str,
    verify_files: bool,
) -> ScrapedPaper | None:
    arxiv_id = str(row["arxiv_id"])
    html_path = resolve_html_path(
        arxiv_id=arxiv_id,
        recorded_path=row["html_path"],
        cache_dir=cache_dir,
        verify_files=verify_files,
    )
    if not html_path:
        return None

    return ScrapedPaper(
        arxiv_id=arxiv_id,
        version=row["version"] or "",
        title=row["title"] or arxiv_id,
        categories=parse_categories(row["categories"]),
        latest_version_date=row["latest_version_date"] or "",
        source_url=row["source_url"] or f"https://arxiv.org/html/{arxiv_id}",
        html_key=object_key_for_path(html_path, cache_dir=cache_dir, prefix=prefix),
        bytes=int(row["bytes"] or 0),
    )


def resolve_html_path(
    *,
    arxiv_id: str,
    recorded_path: str | None,
    cache_dir: Path,
    verify_files: bool,
) -> Path | None:
    candidates: list[Path] = []
    if recorded_path:
        recorded = Path(recorded_path).expanduser()
        if recorded.is_absolute():
            try:
                candidates.append(cache_dir / recorded.relative_to(cache_dir))
            except ValueError:
                pass
        else:
            candidates.append(cache_dir / recorded)

        tail = path_tail_after_cache_marker(recorded)
        if tail:
            candidates.append(cache_dir / tail)

    candidates.append(cache_dir / arxiv_id[:4] / f"{safe_filename(arxiv_id)}.html")

    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if not is_relative_to(resolved, cache_dir):
            continue
        if not verify_files or resolved.is_file():
            return resolved
    return None


def object_key_for_path(path: Path, *, cache_dir: Path, prefix: str) -> str:
    relative = path.resolve().relative_to(cache_dir.resolve()).as_posix()
    prefix_normalized = prefix.strip("/")
    if prefix_normalized:
        return f"{prefix_normalized}/{relative}"
    return relative


def path_tail_after_cache_marker(path: Path) -> Path | None:
    parts = path.parts
    for marker in ("html", "data"):
        if marker not in parts:
            continue
        index = len(parts) - 1 - parts[::-1].index(marker)
        tail_parts = parts[index + 1 :]
        if tail_parts:
            return Path(*tail_parts)
    return None


def parse_categories(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return [category for category in value.split() if category]
    return [str(category) for category in parsed]


def date_part(value: str) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return value[:10]


def safe_filename(arxiv_id: str) -> str:
    return "".join(char if char.isalnum() or char in "_.-" else "_" for char in arxiv_id)


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def metadata_from_local_html(*, html_path: Path | None) -> dict[str, Any]:
    if html_path is None or not html_path.is_file():
        return {"title": "", "abstract": "", "authors": []}

    try:
        html = html_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"title": "", "abstract": "", "authors": []}

    return extract_html_metadata(html)


def print_summary(manifest: dict[str, Any]) -> None:
    dates = manifest["dates"]
    newest = next(iter(dates), None)
    print(
        f"Indexed {manifest['total_papers']} papers across {len(dates)} dates; "
        f"newest={newest or 'none'}; skipped_missing={manifest['skipped_missing_files']}"
    )
    for day, payload in list(dates.items())[:5]:
        print(f"  {day}: {payload['count']}")


def r2_client(args: argparse.Namespace):
    required = {
        "R2_ACCOUNT_ID": args.account_id,
        "R2_ACCESS_KEY_ID": args.access_key_id,
        "R2_SECRET_ACCESS_KEY": args.secret_access_key,
        "R2_BUCKET": args.bucket,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise SystemExit(f"Missing required R2 settings: {', '.join(missing)}")

    return boto3.client(
        "s3",
        endpoint_url=f"https://{args.account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=args.access_key_id,
        aws_secret_access_key=args.secret_access_key,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


if __name__ == "__main__":
    main()
