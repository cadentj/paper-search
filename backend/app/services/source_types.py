"""Shared types for source providers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from app.models.paper import Paper


@dataclass(frozen=True)
class SourceFetchResult:
    papers: list[Paper]
    errors: list[str] = field(default_factory=list)
    skipped_missing_text: dict[str, int] = field(default_factory=dict)


class SourceProvider(Protocol):
    source_type: str

    def count_for_date(self, run_date: date) -> int:
        ...

    def candidates_for_date(self, run_date: date) -> SourceFetchResult:
        ...

    def html_for_paper(self, paper: Paper) -> dict[str, str | None]:
        ...
