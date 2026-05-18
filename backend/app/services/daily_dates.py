from __future__ import annotations

from datetime import date, timedelta

from app.core.config import settings


def fixed_daily_dates() -> list[date]:
    window_days = max(settings.DAILY_DATE_WINDOW_DAYS, 1)
    start = settings.ARXIV_ANCHOR_DATE - timedelta(days=window_days - 1)
    return [
        start + timedelta(days=offset)
        for offset in range(window_days)
    ]


def is_valid_daily_date(value: date) -> bool:
    return value in set(fixed_daily_dates())
