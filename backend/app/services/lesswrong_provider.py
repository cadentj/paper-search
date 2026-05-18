"""LessWrong source — SQLite daily index and R2 HTML access."""

from __future__ import annotations

from app.services.source_provider_base import DbBackedSourceProvider


class LessWrongProvider(DbBackedSourceProvider):
    source_type = "lesswrong"
