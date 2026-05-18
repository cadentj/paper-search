"""Onboarding extraction worker job."""

import json
import uuid
from datetime import datetime, timezone

from app.db.session import SessionLocal
from app.models.job import Job
from app.models.onboarding_extraction import OnboardingExtraction
from app.services.jobs import build_progress, get_or_create_job_for_subject
from app.llm.client import stream_structured_response
from app.llm.config import FILTER_GENERATION_PROFILE
from app.llm.prompts import (
    ONBOARDING_SYSTEM_PROMPT,
    ONBOARDING_USER_PROMPT,
)
from app.llm.schemas import OnboardingFiltersResponse, StreamedFilter


def _normalize_filter(raw: dict) -> dict | None:
    try:
        item = StreamedFilter.model_validate(raw)
    except Exception:
        return None
    return item.model_dump()


def _extract_complete_filter_objects(buffer: str) -> list[dict]:
    decoder = json.JSONDecoder()
    marker = '"proposedFilters"'
    marker_idx = buffer.find(marker)
    if marker_idx == -1:
        return []

    array_start = buffer.find("[", marker_idx)
    if array_start == -1:
        return []

    idx = array_start + 1
    results: list[dict] = []
    while idx < len(buffer):
        while idx < len(buffer) and buffer[idx] in " \n\r\t,":
            idx += 1
        if idx >= len(buffer) or buffer[idx] == "]":
            break
        try:
            obj, next_idx = decoder.raw_decode(buffer, idx)
        except json.JSONDecodeError:
            break
        if isinstance(obj, dict):
            normalized = _normalize_filter(obj)
            if normalized:
                results.append(normalized)
        idx = next_idx

    return results


def _merge_filters(existing: list[dict], incoming: list[dict]) -> list[dict]:
    by_id = {f.get("id"): f for f in existing if f.get("id")}
    merged = list(existing)

    for item in incoming:
        item_id = item.get("id") or str(uuid.uuid4())
        item["id"] = item_id
        if item_id in by_id:
            continue
        by_id[item_id] = item
        merged.append(item)

    return merged


def _resolve_onboarding_job(db, extraction_id: str, job_id: str | None) -> Job:
    if job_id:
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            return job
    return get_or_create_job_for_subject(
        db,
        kind="onboarding_extraction",
        subject_type="onboarding_extraction",
        subject_id=extraction_id,
    )


def extract_onboarding_filters(extraction_id: str, job_id: str | None = None) -> None:
    """Worker job: extract proposed filters from onboarding text."""
    db = SessionLocal()
    try:
        extraction = db.query(OnboardingExtraction).filter(
            OnboardingExtraction.id == extraction_id
        ).first()
        if not extraction:
            return

        job = _resolve_onboarding_job(db, extraction_id, job_id)
        now = datetime.now(timezone.utc)
        extraction.status = "running"
        extraction.updated_at = now
        job.status = "running"
        job.started_at = now
        job.updated_at = now
        job.progress = build_progress(
            stage="extracting_filters",
            current=0,
            total=1,
            message="Extracting proposed filters",
            log=(job.progress or {}).get("log", []),
        )
        db.commit()

        user_prompt = ONBOARDING_USER_PROMPT.format(input_text=extraction.input_text)
        text_buffer = ""
        last_count = 0

        def handle_delta(delta: str) -> None:
            nonlocal text_buffer, last_count
            text_buffer += delta
            parsed_filters = _extract_complete_filter_objects(text_buffer)
            if len(parsed_filters) <= last_count:
                return

            current = list(extraction.proposed_filters or [])
            extraction.proposed_filters = _merge_filters(current, parsed_filters)
            extraction.updated_at = datetime.now(timezone.utc)
            last_count = len(parsed_filters)
            job.progress = build_progress(
                stage="extracting_filters",
                current=last_count,
                total=max(last_count, 1),
                message=f"Extracted {last_count} proposed filters",
                log=(job.progress or {}).get("log", []),
                append_log=False,
                filters_found=last_count,
            )
            job.updated_at = extraction.updated_at
            db.commit()

        result = stream_structured_response(
            system_prompt=ONBOARDING_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_model=OnboardingFiltersResponse,
            on_text_delta=handle_delta,
            profile=FILTER_GENERATION_PROFILE,
        )

        content = result["content"]
        proposed = content.get("proposedFilters", [])

        for f in proposed:
            if "id" not in f:
                f["id"] = str(uuid.uuid4())

        extraction.proposed_filters = _merge_filters(
            list(extraction.proposed_filters or []),
            [_normalize_filter(f) or f for f in proposed],
        )
        extraction.llm_model = result["model"]
        extraction.llm_response_id = result["response_id"]
        extraction.status = "completed"
        extraction.completed_at = datetime.now(timezone.utc)
        extraction.updated_at = datetime.now(timezone.utc)
        final_count = len(extraction.proposed_filters or [])
        job.status = "completed"
        job.completed_at = extraction.completed_at
        job.updated_at = extraction.updated_at
        job.progress = build_progress(
            stage="completed",
            current=final_count,
            total=max(final_count, 1),
            message=f"Completed onboarding extraction with {final_count} filters",
            log=(job.progress or {}).get("log", []),
            filters_found=final_count,
        )
        db.commit()

    except Exception as e:
        db.rollback()
        extraction = db.query(OnboardingExtraction).filter(
            OnboardingExtraction.id == extraction_id
        ).first()
        if extraction:
            now = datetime.now(timezone.utc)
            extraction.status = "failed"
            extraction.error = str(e)
            extraction.updated_at = now
            job = _resolve_onboarding_job(db, extraction_id, job_id)
            job.status = "failed"
            job.error = extraction.error
            job.completed_at = now
            job.updated_at = now
            job.progress = build_progress(
                stage="failed",
                current=(job.progress or {}).get("current", 0),
                total=(job.progress or {}).get("total", 1),
                message=f"Onboarding extraction failed: {e}",
                log=(job.progress or {}).get("log", []),
            )
            db.commit()
        raise
    finally:
        db.close()
