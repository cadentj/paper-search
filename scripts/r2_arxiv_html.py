#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3>=1.34.0"]
# ///
"""Upload and sample cached arXiv HTML files in Cloudflare R2."""

from __future__ import annotations

import argparse
import mimetypes
import os
import random
from pathlib import Path

import boto3
from botocore.config import Config


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = REPO_ROOT / "data" / "arxiv_html_cache" / "html"


def main() -> None:
    args = parse_args()
    client = r2_client(args)
    if args.command == "upload":
        upload_html(client, args)
    elif args.command == "sample":
        sample_html(client, args)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", default=os.environ.get("R2_ACCOUNT_ID"))
    parser.add_argument("--access-key-id", default=os.environ.get("R2_ACCESS_KEY_ID"))
    parser.add_argument("--secret-access-key", default=os.environ.get("R2_SECRET_ACCESS_KEY"))
    parser.add_argument("--bucket", default=os.environ.get("R2_BUCKET"))
    parser.add_argument("--prefix", default="arxiv-html/")
    subparsers = parser.add_subparsers(dest="command", required=True)

    upload = subparsers.add_parser("upload", help="Upload local cached HTML files to R2.")
    upload.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    upload.add_argument("--limit", type=int, default=None)
    upload.add_argument("--dry-run", action="store_true")

    sample = subparsers.add_parser("sample", help="Print random R2 object keys.")
    sample.add_argument("--count", type=int, default=50)
    return parser.parse_args()


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


def upload_html(client, args: argparse.Namespace) -> None:
    cache_dir = Path(args.cache_dir).expanduser().resolve()
    if not cache_dir.exists():
        raise SystemExit(f"Cache dir not found: {cache_dir}")

    files = sorted(cache_dir.rglob("*.html"))
    if args.limit is not None:
        files = files[: args.limit]

    uploaded = 0
    for path in files:
        relative = path.relative_to(cache_dir)
        key = f"{args.prefix.rstrip('/')}/{relative.as_posix()}"
        if args.dry_run:
            print(f"DRY RUN {path} -> s3://{args.bucket}/{key}")
            continue
        content_type = mimetypes.guess_type(path.name)[0] or "text/html"
        client.upload_file(
            str(path),
            args.bucket,
            key,
            ExtraArgs={
                "ContentType": content_type,
                "CacheControl": "public, max-age=31536000, immutable",
            },
        )
        uploaded += 1
        if uploaded % 100 == 0:
            print(f"Uploaded {uploaded}/{len(files)}")

    print(f"{'Would upload' if args.dry_run else 'Uploaded'} {len(files)} files")


def sample_html(client, args: argparse.Namespace) -> None:
    keys = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=args.bucket, Prefix=args.prefix):
        keys.extend(
            item["Key"]
            for item in page.get("Contents", [])
            if item.get("Key", "").endswith(".html")
        )
    for key in random.sample(keys, min(args.count, len(keys))):
        print(key)


if __name__ == "__main__":
    main()
