"""Shared types for source providers."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from app.models.paper import Paper


class SourceProvider(Protocol):
    source_type: str

    def count_for_date(self, run_date: date) -> int:
        ...

    def papers_for_date(self, run_date: date) -> list[Paper]:
        ...

    def html_for_paper(self, paper: Paper) -> dict[str, str | None]:
        ...
