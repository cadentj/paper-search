#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27.0"]
# ///
"""Probe LessWrong request status codes for a short fixed window."""

from __future__ import annotations

import argparse
import time

import httpx


URLS = [
    "https://www.lesswrong.com/posts/gidrFxE5hdQWCrXxn/why-is-lesswrong-blocking-wget-and-curl-scrape",
    "https://www.lesswrong.com/s/h8DebDmuode4TMcRj/p/LJiGhpq8w4Badr5KJ",
]


def main() -> None:
    args = parse_args()
    deadline = time.monotonic() + args.seconds
    headers = {"User-Agent": args.user_agent}
    print("phase,rps,request,status,elapsed_ms,retry_after,url", flush=True)

    with httpx.Client(timeout=args.timeout, follow_redirects=True, headers=headers) as client:
        for phase, rps in enumerate(args.rps, start=1):
            interval = 1.0 / rps
            phase_end = min(deadline, time.monotonic() + args.phase_seconds)
            request_index = 0
            while time.monotonic() < phase_end and time.monotonic() < deadline:
                url = URLS[request_index % len(URLS)]
                started = time.monotonic()
                retry_after = ""
                try:
                    response = client.get(url)
                    status = str(response.status_code)
                    retry_after = response.headers.get("retry-after", "")
                    response.read()
                except httpx.HTTPError as exc:
                    status = type(exc).__name__

                elapsed_ms = (time.monotonic() - started) * 1000
                print(
                    f"{phase},{rps},{request_index + 1},{status},"
                    f"{elapsed_ms:.0f},{retry_after},{url}",
                    flush=True,
                )

                sleep_for = interval - (time.monotonic() - started)
                if sleep_for > 0:
                    time.sleep(sleep_for)
                request_index += 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=30)
    parser.add_argument("--phase-seconds", type=int, default=6)
    parser.add_argument("--rps", type=float, nargs="+", default=[0.5, 1, 2, 4, 8])
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--user-agent", default="paper-search-rate-probe/0.1 contact: local-research")
    return parser.parse_args()


if __name__ == "__main__":
    main()
