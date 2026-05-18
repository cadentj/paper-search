#!/usr/bin/env python3
"""Sync public R2 daily indexes into the app SQLite database."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.index_sync import sync_public_indexes  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    summary = sync_public_indexes()
    for source_type, dates in summary.items():
        synced = sum(1 for total, searchable in dates.values() if total > 0)
        logger.info(
            "%s: synced %s dates (%s total date slots in window)",
            source_type,
            synced,
            len(dates),
        )


if __name__ == "__main__":
    main()
