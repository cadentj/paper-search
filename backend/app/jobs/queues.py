from __future__ import annotations

from collections.abc import Callable
from typing import Any
from redis import Redis
from rq import Queue

from app.config import settings


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


def enqueue_for_job(
    job: SQLAJob, func: Callable[..., Any], *args: Any, **kwargs: Any
) -> object:
    queue = Queue(job.queue_name, connection=Redis.from_url(settings.REDIS_URL))
    return queue.enqueue(func, *args, **kwargs)
