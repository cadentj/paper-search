"""Entry point for sync-public-index."""

from __future__ import annotations

import logging

from tqdm import tqdm

from paper_search_core.daily_dates import DAILY_SEARCH_DATE_SET
from paper_search_scripts.config import SyncSettings, resolve_sqlite_path
from paper_search_scripts.sync import sync_public_indexes

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
for _logger_name in ("httpx", "httpcore"):
    logging.getLogger(_logger_name).setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def main() -> None:
    settings = SyncSettings()
    db_path = resolve_sqlite_path(settings.DATABASE_URL)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    date_slots = len(DAILY_SEARCH_DATE_SET)
    with tqdm(
        total=date_slots * 2,
        desc="syncing public index",
        unit="date",
        dynamic_ncols=True,
    ) as progress:
        summary = sync_public_indexes(settings, progress=progress)

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
