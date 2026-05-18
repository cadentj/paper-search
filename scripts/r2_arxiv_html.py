#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3>=1.34.0", "tqdm>=4.66.0"]
# ///
"""Upload and sample cached arXiv HTML files in Cloudflare R2."""

from __future__ import annotations

import argparse
import mimetypes
import os
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from tqdm import tqdm


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = REPO_ROOT / "data" / "arxiv_html_cache" / "html"


def main() -> None:
    args = parse_args()
    client = r2_client(args, max_pool_connections=getattr(args, "workers", 16) * 2)
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
    parser.add_argument("--prefix", default="data/")
    subparsers = parser.add_subparsers(dest="command", required=True)

    upload = subparsers.add_parser("upload", help="Upload local cached HTML files to R2.")
    upload.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    upload.add_argument("--limit", type=int, default=None)
    upload.add_argument("--dry-run", action="store_true")
    upload.add_argument("--workers", type=int, default=16)
    upload.add_argument(
        "--skip-existing",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip keys that already exist in R2. Use --no-skip-existing to overwrite.",
    )

    sample = subparsers.add_parser("sample", help="Print random R2 object keys.")
    sample.add_argument("--count", type=int, default=50)
    return parser.parse_args()


@dataclass(frozen=True)
class UploadTask:
    path: Path
    key: str


@dataclass(frozen=True)
class UploadResult:
    status: str
    key: str
    error: str = ""


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


def upload_html(client, args: argparse.Namespace) -> None:
    cache_dir = Path(args.cache_dir).expanduser().resolve()
    if not cache_dir.exists():
        raise SystemExit(f"Cache dir not found: {cache_dir}")

    files = sorted(cache_dir.rglob("*.html"))
    if args.limit is not None:
        files = files[: args.limit]

    tasks = [
        UploadTask(
            path=path,
            key=f"{args.prefix.rstrip('/')}/{path.relative_to(cache_dir).as_posix()}",
        )
        for path in files
    ]

    if args.dry_run:
        for task in tasks:
            print(f"DRY RUN {task.path} -> s3://{args.bucket}/{task.key}")
        print(f"Would upload {len(tasks)} files")
        return

    stats = {"uploaded": 0, "skipped": 0, "error": 0}
    with ThreadPoolExecutor(max_workers=max(args.workers, 1)) as executor, tqdm(
        total=len(tasks),
        desc="uploading",
        unit="file",
        dynamic_ncols=True,
    ) as progress:
        futures = [executor.submit(upload_one, client, args, task) for task in tasks]
        _set_progress(progress, stats)
        for future in as_completed(futures):
            result = future.result()
            stats[result.status] += 1
            if result.status == "error":
                tqdm.write(f"{result.key} error {result.error}")
            progress.update(1)
            _set_progress(progress, stats)

    print(
        f"Uploaded {stats['uploaded']} files, skipped {stats['skipped']}, "
        f"errors {stats['error']}"
    )


def upload_one(client, args: argparse.Namespace, task: UploadTask) -> UploadResult:
    try:
        if args.skip_existing and object_exists(client, args.bucket, task.key):
            return UploadResult(status="skipped", key=task.key)

        content_type = mimetypes.guess_type(task.path.name)[0] or "text/html"
        client.upload_file(
            str(task.path),
            args.bucket,
            task.key,
            ExtraArgs={
                "ContentType": content_type,
                "CacheControl": "public, max-age=31536000, immutable",
            },
        )
    except Exception as exc:
        return UploadResult(status="error", key=task.key, error=str(exc))

    return UploadResult(status="uploaded", key=task.key)


def object_exists(client, bucket: str, key: str) -> bool:
    try:
        client.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        status_code = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        error_code = exc.response.get("Error", {}).get("Code")
        if status_code == 404 or error_code in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise
    return True


def _set_progress(progress: tqdm, stats: dict[str, int]) -> None:
    progress.set_postfix(
        uploaded=stats["uploaded"],
        skipped=stats["skipped"],
        error=stats["error"],
    )


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
