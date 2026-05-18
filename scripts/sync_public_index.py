#!/usr/bin/env python3
"""Sync public R2 daily indexes into the app SQLite database."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from tqdm import tqdm

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.daily_dates import DAILY_SEARCH_DATE_SET  # noqa: E402
from app.services.index_sync import sync_public_indexes  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
for _logger_name in ("httpx", "httpcore"):
    logging.getLogger(_logger_name).setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def main() -> None:
    date_slots = len(DAILY_SEARCH_DATE_SET)
    with tqdm(
        total=date_slots * 2,
        desc="syncing public index",
        unit="date",
        dynamic_ncols=True,
    ) as progress:
        summary = sync_public_indexes(progress=progress)

    for source_type, dates in summary.items():
        synced = sum(1 for total, _searchable in dates.values() if total > 0)
        logger.info(
            "%s: synced %s dates (%s total date slots in window)",
            source_type,
            synced,
            len(dates),
        )


if __name__ == "__main__":
    main()
