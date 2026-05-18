#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3>=1.34.0", "tqdm>=4.66.0"]
# ///
"""Upload cached LessWrong HTML files to Cloudflare R2."""

from __future__ import annotations

import argparse
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from tqdm import tqdm


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = REPO_ROOT / "data" / "lesswrong_html_cache" / "html"


@dataclass(frozen=True)
class UploadTask:
    path: Path
    key: str


def main() -> None:
    args = parse_args()
    client = r2_client(args)
    upload_html(client, args)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", default=os.environ.get("R2_ACCOUNT_ID"))
    parser.add_argument("--access-key-id", default=os.environ.get("R2_ACCESS_KEY_ID"))
    parser.add_argument("--secret-access-key", default=os.environ.get("R2_SECRET_ACCESS_KEY"))
    parser.add_argument("--bucket", default=os.environ.get("R2_BUCKET"))
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    parser.add_argument("--prefix", default="data/")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--skip-existing", action=argparse.BooleanOptionalAction, default=True)
    return parser.parse_args()


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
        for future in as_completed(futures):
            status, key, error = future.result()
            stats[status] += 1
            if status == "error":
                tqdm.write(f"{key} error {error}")
            progress.update(1)
            progress.set_postfix(**stats)
    print(f"Uploaded {stats['uploaded']} files, skipped {stats['skipped']}, errors {stats['error']}")


def upload_one(client, args: argparse.Namespace, task: UploadTask) -> tuple[str, str, str]:
    try:
        if args.skip_existing and object_exists(client, args.bucket, task.key):
            return "skipped", task.key, ""
        client.upload_file(
            str(task.path),
            args.bucket,
            task.key,
            ExtraArgs={
                "ContentType": "text/html; charset=utf-8",
                "CacheControl": "public, max-age=31536000, immutable",
            },
        )
    except Exception as exc:
        return "error", task.key, str(exc)
    return "uploaded", task.key, ""


def object_exists(client, bucket: str, key: str) -> bool:
    try:
        client.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        status_code = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        error_code = exc.response.get("Error", {}).get("Code")
        # R2/S3 often returns 403 instead of 404 when HeadObject is unavailable
        # or the caller lacks ListBucket permission on missing keys.
        if status_code in {403, 404} or error_code in {
            "403",
            "404",
            "NoSuchKey",
            "NotFound",
            "Forbidden",
            "AccessDenied",
        }:
            return False
        raise
    return True


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
        config=Config(signature_version="s3v4", max_pool_connections=max(args.workers * 2, 1)),
        region_name="auto",
    )


if __name__ == "__main__":
    main()
