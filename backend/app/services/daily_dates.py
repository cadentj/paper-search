from __future__ import annotations

from datetime import date, timedelta

# Daily search window: 31 days ending 2026-05-14 (matches scrape script defaults).
DAILY_SEARCH_END = date(2026, 5, 14)
DAILY_SEARCH_START = date(2026, 4, 14)
DAILY_SEARCH_DATES: tuple[date, ...] = tuple(
    DAILY_SEARCH_START + timedelta(days=offset)
    for offset in range((DAILY_SEARCH_END - DAILY_SEARCH_START).days + 1)
)
DAILY_SEARCH_DATE_SET: frozenset[date] = frozenset(DAILY_SEARCH_DATES)
DEFAULT_DAILY_SEARCH_DATE = DAILY_SEARCH_END
