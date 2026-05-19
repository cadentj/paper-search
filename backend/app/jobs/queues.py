from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.jobs.queue import get_queue
from app.models.job import SQLAJob

INTERACTIVE = "interactive"
REPORTS = "reports"
IDEA_MAPS = "idea_maps"

KIND_TO_QUEUE: dict[str, str] = {
    "daily_search": REPORTS,
    "daily_search_summary": REPORTS,
    "idea_map": IDEA_MAPS,
    "feedback_reflection": INTERACTIVE,
    "document_processing": INTERACTIVE,
    "onboarding_generation": INTERACTIVE,
    "onboarding_extraction": INTERACTIVE,
    "scholar_import": INTERACTIVE,
}


def queue_for_kind(kind: str) -> str:
    try:
        return KIND_TO_QUEUE[kind]
    except KeyError as exc:
        raise ValueError(f"Unknown job kind for queue routing: {kind}") from exc


def resolve_queue_name(job: SQLAJob) -> str:
    return job.queue_name or queue_for_kind(job.kind)


def enqueue_for_job(
    job: SQLAJob, func: Callable[..., Any], *args: Any, **kwargs: Any
) -> object:
    return get_queue(resolve_queue_name(job)).enqueue(func, *args, **kwargs)
