#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "beautifulsoup4>=4.12.0",
#   "boto3>=1.34.0",
#   "httpx>=0.27.0",
#   "lxml>=5.0.0",
#   "tqdm>=4.66.0",
# ]
# ///
"""Migrate a monolithic arXiv R2 index to sharded manifests and upload."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from arxiv_html_metadata import (
    fetch_metadata_from_public_html,
    fetch_metadata_from_r2,
    html_key_for_arxiv_id,
)
from arxiv_index import (
    DEFAULT_DATE_INDEX_PREFIX,
    DEFAULT_HTML_PREFIX,
    DEFAULT_INDEX_KEY,
    apply_metadata_to_index,
    collect_papers_missing_abstract,
    count_papers,
    is_monolithic_index,
    is_sharded_manifest,
    split_monolithic_to_sharded,
)
from r2_index import json_body, upload_sharded_index
from arxiv_metadata import normalize_arxiv_id


def main() -> None:
    args = parse_args()

    if args.upload_only:
        upload_from_output_dir(args)
        return

    index = load_index(args)
    paper_count = count_papers(index)
    print(f"Loaded index with {paper_count} papers across {len(index.get('dates') or {})} dates")

    if is_sharded_manifest(index) and not args.force:
        print("Index is already a sharded manifest. Re-run with --force to rebuild shards.")
        return

    working_index = index
    if is_sharded_manifest(index) and args.force:
        working_index = load_sharded_index_as_monolithic(args, index)

    if is_monolithic_index(working_index):
        missing = collect_papers_missing_abstract(
            working_index,
            normalize_arxiv_id=normalize_arxiv_id,
            html_key_for_arxiv_id=html_key_for_arxiv_id,
        )
        print(f"{len(missing)} papers missing abstract metadata")
        if missing and not args.skip_enrich:
            if args.via_public_url:
                print(
                    f"Fetching HTML abstracts for {len(missing)} papers via public URL "
                    f"({args.workers} workers)...",
                    flush=True,
                )
                metadata_by_id = fetch_metadata_from_public_html(
                    missing,
                    public_base_url=args.public_base_url,
                    workers=args.workers,
                    html_head_bytes=args.html_head_bytes,
                )
            else:
                print(
                    f"Fetching HTML abstracts for {len(missing)} papers via R2 API "
                    f"({args.workers} workers)...",
                    flush=True,
                )
                fetch_client = r2_client(
                    args,
                    max_pool_connections=max(args.workers * 2, 32),
                )
                metadata_by_id = fetch_metadata_from_r2(
                    missing,
                    client=fetch_client,
                    bucket=args.bucket,
                    workers=args.workers,
                    html_head_bytes=args.html_head_bytes,
                )
            print("Merging metadata into index...", flush=True)
            enriched, unresolved = apply_metadata_to_index(
                working_index,
                metadata_by_id,
                normalize_arxiv_id=normalize_arxiv_id,
            )
            print(
                f"Enriched {enriched} papers from R2 HTML; "
                f"{unresolved} had no parseable abstract"
            )
            working_index["metadata_enriched_at"] = datetime.now(timezone.utc).isoformat()

    manifest, date_shards = split_monolithic_to_sharded(
        working_index,
        html_prefix=args.html_prefix,
        date_index_prefix=args.date_index_prefix,
    )

    print("Writing sharded index files...", flush=True)
    print_summary(manifest, date_shards)
    write_local_output(args, manifest, date_shards)

    if args.dry_run:
        print("Dry run complete. No uploads performed.")
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
    parser.add_argument(
        "--index-key",
        default=os.environ.get("ARXIV_HTML_INDEX_PATH", DEFAULT_INDEX_KEY),
    )
    parser.add_argument("--html-prefix", default=DEFAULT_HTML_PREFIX)
    parser.add_argument("--date-index-prefix", default=DEFAULT_DATE_INDEX_PREFIX)
    parser.add_argument(
        "--public-base-url",
        default=os.environ.get("ARXIV_HTML_PUBLIC_BASE_URL", ""),
    )
    parser.add_argument(
        "--input",
        help="Optional local monolithic index JSON. If omitted, downloads --index-key from R2.",
    )
    parser.add_argument(
        "--output-dir",
        help="Optional local directory to write manifest and date shards.",
    )
    parser.add_argument(
        "--upload-only",
        action="store_true",
        help="Upload an existing --output-dir to R2 without re-downloading or enriching.",
    )
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument(
        "--html-head-bytes",
        type=int,
        default=262_144,
        help="Fetch only the first N bytes of HTML when enriching (0 = full file).",
    )
    parser.add_argument(
        "--via-public-url",
        action="store_true",
        help="Fetch HTML via ARXIV_HTML_PUBLIC_BASE_URL instead of the R2 API.",
    )
    parser.add_argument("--skip-enrich", action="store_true")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild date shards even if the manifest is already sharded.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build local output but do not upload to R2 (enrichment still runs).",
    )
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args()


def upload_from_output_dir(args: argparse.Namespace) -> None:
    if not args.output_dir:
        raise SystemExit("--upload-only requires --output-dir")

    output_dir = Path(args.output_dir).expanduser().resolve()
    manifest_path = output_dir / "papers-by-date.json"
    dates_dir = output_dir / "dates"
    if not manifest_path.is_file() or not dates_dir.is_dir():
        raise SystemExit(f"Expected {manifest_path} and {dates_dir}/")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    date_shards: dict[str, dict[str, Any]] = {}
    for day, payload in (manifest.get("dates") or {}).items():
        shard_path = dates_dir / f"{day}.json"
        if not shard_path.is_file():
            index_key = str(payload.get("index_key") or "")
            raise SystemExit(f"Missing local date shard for {day}: {shard_path} (index_key={index_key})")
        date_shards[day] = json.loads(shard_path.read_text(encoding="utf-8"))

    print_summary(manifest, date_shards)
    if args.dry_run:
        print("Dry run complete. No uploads performed.")
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


def load_index(args: argparse.Namespace) -> dict[str, Any]:
    if args.input:
        return json.loads(Path(args.input).expanduser().read_text(encoding="utf-8"))

    client = r2_client(args)
    response = client.get_object(Bucket=args.bucket, Key=args.index_key)
    return json.loads(response["Body"].read())


def load_sharded_index_as_monolithic(
    args: argparse.Namespace,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    client = r2_client(args)
    dates: dict[str, dict[str, Any]] = {}
    for day, payload in (manifest.get("dates") or {}).items():
        index_key = str(payload.get("index_key") or "")
        if not index_key:
            continue
        response = client.get_object(Bucket=args.bucket, Key=index_key)
        shard = json.loads(response["Body"].read())
        dates[day] = {"count": len(shard.get("papers") or []), "papers": shard.get("papers") or []}

    return {
        "schema_version": manifest.get("schema_version"),
        "generated_at": manifest.get("generated_at"),
        "html_prefix": manifest.get("html_prefix"),
        "date_index_prefix": manifest.get("date_index_prefix"),
        "skipped_missing_files": manifest.get("skipped_missing_files", 0),
        "total_papers": manifest.get("total_papers"),
        "metadata_enriched_at": manifest.get("metadata_enriched_at"),
        "dates": dates,
    }


def write_local_output(
    args: argparse.Namespace,
    manifest: dict[str, Any],
    date_shards: dict[str, dict[str, Any]],
) -> None:
    if not args.output_dir:
        return

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "papers-by-date.json"
    manifest_path.write_text(json_body(manifest, pretty=args.pretty), encoding="utf-8")
    dates_dir = output_dir / "dates"
    dates_dir.mkdir(parents=True, exist_ok=True)
    for day, shard in date_shards.items():
        (dates_dir / f"{day}.json").write_text(json_body(shard, pretty=args.pretty), encoding="utf-8")
    print(f"Wrote manifest and {len(date_shards)} date shards to {output_dir}")


def print_summary(manifest: dict[str, Any], date_shards: dict[str, dict[str, Any]]) -> None:
    dates = manifest.get("dates") or {}
    newest = next(iter(dates), None)
    print(
        f"Prepared manifest for {manifest.get('total_papers', 0)} papers "
        f"across {len(dates)} dates; newest={newest or 'none'}"
    )
    for day, payload in list(dates.items())[:5]:
        shard_count = date_shards.get(day, {}).get("count", payload.get("count"))
        print(f"  {day}: {shard_count}")


def r2_client(args: argparse.Namespace, *, max_pool_connections: int = 32):
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
        config=Config(
            signature_version="s3v4",
            max_pool_connections=max(max_pool_connections, 1),
        ),
        region_name="auto",
    )


if __name__ == "__main__":
    main()
