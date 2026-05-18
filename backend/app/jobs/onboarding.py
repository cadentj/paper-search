"""Onboarding extraction worker job."""

import json
import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel
from app.db.session import SessionLocal
from app.models.onboarding_extraction import OnboardingExtraction
from app.llm.client import stream_structured_response
from app.llm.prompts import (
    ONBOARDING_SYSTEM_PROMPT,
    ONBOARDING_USER_PROMPT,
)


class StreamedFilter(BaseModel):
    id: str
    name: str
    description: str
    mode: Literal["warrants", "answers", "relevance"]


class OnboardingFiltersResponse(BaseModel):
    proposedFilters: list[StreamedFilter]


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


def extract_onboarding_filters(extraction_id: str) -> None:
    """Worker job: extract proposed filters from onboarding text."""
    db = SessionLocal()
    try:
        extraction = db.query(OnboardingExtraction).filter(
            OnboardingExtraction.id == extraction_id
        ).first()
        if not extraction:
            return

        extraction.status = "running"
        extraction.updated_at = datetime.now(timezone.utc)
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
            db.commit()

        result = stream_structured_response(
            system_prompt=ONBOARDING_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            text_format=OnboardingFiltersResponse,
            on_text_delta=handle_delta,
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
        db.commit()

    except Exception as e:
        db.rollback()
        extraction = db.query(OnboardingExtraction).filter(
            OnboardingExtraction.id == extraction_id
        ).first()
        if extraction:
            extraction.status = "failed"
            extraction.error = str(e)
            extraction.updated_at = datetime.now(timezone.utc)
            db.commit()
        raise
    finally:
        db.close()
