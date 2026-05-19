"""Idea map generation worker job."""

from concurrent.futures import ThreadPoolExecutor
import json
import logging

import httpx
from queue import Empty, Queue
from datetime import datetime, timezone

from sqlalchemy.orm.attributes import flag_modified

from app.db.session import database
from app.models.job import Job
from app.models.paper import Paper
from app.models.idea_map import IdeaMap
from app.services import papers as papers_service
from app.services.jobs import job_progress, set_job_status
from app.core.config import LLM_MAX_CONCURRENCY
from app.utils.html_parser import (
    MAX_PROMPT_BLOCKS,
    blocks_to_prompt_text,
    citation_validation_diagnostics,
    parse_arxiv_html,
)
from app.llm.client import stream_structured_response
from app.llm.config import IDEA_MAP_PROFILE
from app.llm.prompts import (
    IDEA_MAP_CLAIMS_SYSTEM_PROMPT,
    IDEA_MAP_CLAIMS_USER_PROMPT,
    IDEA_MAP_WARRANTS_SYSTEM_PROMPT,
    IDEA_MAP_WARRANTS_USER_PROMPT,
)
from app.llm.schemas import (
    IdeaMapClaimsResponse,
    IdeaMapCoreClaim,
    IdeaMapWarrant,
    IdeaMapWarrantsResponse,
)
from tqdm import tqdm


logger = logging.getLogger(__name__)


def generate_idea_map(idea_map_id: str, job_id: str | None = None) -> None:
    """Worker job: generate idea map from arXiv HTML."""
    with database.session() as db:
        try:
            idea_map = db.query(IdeaMap).filter(IdeaMap.id == idea_map_id).first()
            if not idea_map:
                return

            job = papers_service.resolve_idea_map_job(db, idea_map_id, job_id)
            papers_service.mark_idea_map_running(db, idea_map, job)

            paper = db.query(Paper).filter(Paper.id == idea_map.paper_id).first()
            if not paper or paper.source_type != "arxiv" or not paper.source_id:
                papers_service.mark_idea_map_skipped(
                    db,
                    idea_map,
                    job,
                    "Paper not found or not an arXiv paper with source_id",
                )
                return

            html_url = paper.html_url or paper.source_url
            idea_map.source_url = html_url

            html_content = None
            if paper.html_url:
                try:
                    response = httpx.get(
                        paper.html_url, timeout=30.0, follow_redirects=True
                    )
                    response.raise_for_status()
                    html_content = response.text
                except httpx.HTTPError:
                    html_content = None
            if not html_content:
                idea_map.status = "skipped"
                idea_map.dropped_reason = f"HTML not found for {paper.source_id}"
                idea_map.updated_at = datetime.now(timezone.utc)
                set_job_status(job, status="skipped")
                db.commit()
                return

            blocks = parse_arxiv_html(html_content, exclude_back_matter=True)
            if not blocks:
                idea_map.status = "skipped"
                idea_map.dropped_reason = "HTML could not be parsed into addressable blocks"
                idea_map.updated_at = datetime.now(timezone.utc)
                set_job_status(job, status="skipped")
                db.commit()
                return

            prompt_blocks = blocks[:MAX_PROMPT_BLOCKS]
            blocks_text = blocks_to_prompt_text(prompt_blocks)
            block_map = {block.block_id: block for block in prompt_blocks}
            response_ids: list[str] = []
            llm_model = ""

            idea_map.status = "claims_running"
            _set_claims(idea_map, [])
            idea_map.updated_at = datetime.now(timezone.utc)
            db.commit()

            with tqdm(
                total=None,
                desc="idea-map claims",
                unit="claim",
                dynamic_ncols=True,
                disable=None,
            ) as claims_progress:
                claims_result = _stream_claims(db, idea_map, blocks_text, claims_progress)
                raw_claims = claims_result["content"].get("claims", [])
                normalized_claims = [
                    normalized for raw in raw_claims
                    if (normalized := _normalize_claim(raw))
                ]
                if len(normalized_claims) > claims_progress.n:
                    claims_progress.update(len(normalized_claims) - claims_progress.n)
                claims_progress.set_postfix(claims=len(normalized_claims))

            llm_model = claims_result["model"] or llm_model
            if claims_result["response_id"]:
                response_ids.append(claims_result["response_id"])

            if normalized_claims:
                _set_claims(
                    idea_map,
                    _merge_claims(list(idea_map.claims or []), normalized_claims),
                )
                idea_map.updated_at = datetime.now(timezone.utc)
                db.commit()

            claims = list(idea_map.claims or [])
            logger.info(
                "idea_map run=%s paper=%s arxiv=%s streamed_claims=%s final_claims=%s blocks=%s",
                idea_map.id,
                paper.id,
                paper.source_id,
                len(idea_map.claims or []),
                len(claims),
                len(blocks),
            )

            if not claims:
                idea_map.status = "completed"
                idea_map.llm_model = llm_model
                idea_map.llm_response_id = ",".join(response_ids)
                idea_map.updated_at = datetime.now(timezone.utc)
                set_job_status(job, status="completed")
                db.commit()
                return

            idea_map.status = "warrants_running"
            idea_map.updated_at = datetime.now(timezone.utc)
            job.progress = job_progress(total=len(claims))
            db.commit()

            warrant_queue: Queue[tuple[str, list[dict]]] = Queue()
            rejected_warrant_count = 0
            rejected_warrant_keys: set[tuple[str, str]] = set()
            warrant_failures = 0
            valid_warrant_count = _count_warrants(idea_map.claims)
            max_workers = max(1, min(len(claims), LLM_MAX_CONCURRENCY))
            with tqdm(
                total=len(claims),
                desc="idea-map warrants",
                unit="claim",
                dynamic_ncols=True,
                disable=None,
            ) as warrants_progress, ThreadPoolExecutor(max_workers=max_workers) as executor:
                _set_warrant_progress(
                    warrants_progress,
                    valid=valid_warrant_count,
                    rejected=rejected_warrant_count,
                    failures=warrant_failures,
                )
                future_to_claim = {
                    executor.submit(
                        _stream_warrants_for_claim,
                        claim,
                        blocks_text,
                        warrant_queue,
                    ): claim
                    for claim in claims
                }
                pending = set(future_to_claim)

                while pending:
                    try:
                        claim_id, warrants = warrant_queue.get(timeout=0.2)
                        logger.info(
                            "idea_map run=%s paper=%s claim=%s streamed_warrants normalized_count=%s preview=%s",
                            idea_map.id,
                            paper.id,
                            claim_id,
                            len(warrants),
                            _json_preview(warrants),
                        )
                        rejected_warrant_count += _persist_warrants(
                            db,
                            idea_map,
                            prompt_blocks,
                            block_map,
                            claim_id,
                            warrants,
                            rejected_warrant_keys,
                        )
                        valid_warrant_count = _count_warrants(idea_map.claims)
                        _set_warrant_progress(
                            warrants_progress,
                            valid=valid_warrant_count,
                            rejected=rejected_warrant_count,
                            failures=warrant_failures,
                        )
                    except Empty:
                        pass

                    done = {future for future in pending if future.done()}
                    for future in done:
                        pending.remove(future)
                        claim = future_to_claim[future]
                        try:
                            result = future.result()
                            llm_model = result["model"] or llm_model
                            if result["response_id"]:
                                response_ids.append(result["response_id"])
                            raw_warrants = result["content"].get("warrants", [])
                            final_warrants = []
                            dropped_warrants = 0
                            for raw in raw_warrants:
                                normalized = _normalize_warrant(
                                    raw,
                                    idea_map_id=idea_map.id,
                                    paper_id=paper.id,
                                    claim_id=claim.get("id", ""),
                                )
                                if normalized:
                                    final_warrants.append(normalized)
                                else:
                                    dropped_warrants += 1
                            logger.info(
                                "idea_map run=%s paper=%s claim=%s warrant_llm_response raw_count=%s normalized_count=%s dropped_count=%s raw_preview=%s",
                                idea_map.id,
                                paper.id,
                                claim.get("id", ""),
                                len(raw_warrants),
                                len(final_warrants),
                                dropped_warrants,
                                _json_preview(raw_warrants),
                            )
                            rejected_warrant_count += _persist_warrants(
                                db,
                                idea_map,
                                prompt_blocks,
                                block_map,
                                claim["id"],
                                final_warrants,
                                rejected_warrant_keys,
                            )
                            valid_warrant_count = _count_warrants(idea_map.claims)
                        except Exception:
                            warrant_failures += 1
                            tqdm.write(
                                f"Idea map warrant generation failed for "
                                f"{paper.source_id} claim={claim.get('id', '')}"
                            )
                            logger.exception(
                                "idea_map run=%s paper=%s claim=%s warrant_generation_failed",
                                idea_map.id,
                                paper.id,
                                claim.get("id", ""),
                            )
                        warrants_progress.update(1)
                        db.commit()
                        _set_warrant_progress(
                            warrants_progress,
                            valid=valid_warrant_count,
                            rejected=rejected_warrant_count,
                            failures=warrant_failures,
                        )

                while True:
                    try:
                        claim_id, warrants = warrant_queue.get_nowait()
                    except Empty:
                        break
                    logger.info(
                        "idea_map run=%s paper=%s claim=%s streamed_warrants normalized_count=%s preview=%s",
                        idea_map.id,
                        paper.id,
                        claim_id,
                        len(warrants),
                        _json_preview(warrants),
                    )
                    rejected_warrant_count += _persist_warrants(
                        db,
                        idea_map,
                        prompt_blocks,
                        block_map,
                        claim_id,
                        warrants,
                        rejected_warrant_keys,
                    )
                    valid_warrant_count = _count_warrants(idea_map.claims)
                    _set_warrant_progress(
                        warrants_progress,
                        valid=valid_warrant_count,
                        rejected=rejected_warrant_count,
                        failures=warrant_failures,
                    )

            if rejected_warrant_count:
                tqdm.write(
                    f"Idea map rejected {rejected_warrant_count} invalid warrant "
                    f"citations for {paper.source_id}"
                )

            logger.info(
                "idea_map run=%s paper=%s validated_claims=%s validated_warrants=%s rejected_warrants=%s warrant_failures=%s",
                idea_map.id,
                paper.id,
                len(idea_map.claims or []),
                sum(len(claim.get("warrants", [])) for claim in idea_map.claims or []),
                rejected_warrant_count,
                warrant_failures,
            )
            _set_claims(idea_map, list(idea_map.claims or []))
            idea_map.llm_model = llm_model
            idea_map.llm_response_id = ",".join(response_ids)
            idea_map.status = "completed"
            idea_map.updated_at = datetime.now(timezone.utc)
            set_job_status(job, status="completed")
            db.commit()

        except Exception as e:
            db.rollback()
            idea_map = db.query(IdeaMap).filter(IdeaMap.id == idea_map_id).first()
            if idea_map:
                job = papers_service.resolve_idea_map_job(db, idea_map_id, job_id)
                papers_service.fail_idea_map(db, idea_map, job, str(e))
            raise


def _preview(value: object, limit: int = 500) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _stream_claims(
    db,
    idea_map: IdeaMap,
    blocks_text: str,
    progress: tqdm | None = None,
) -> dict:
    text_buffer = ""
    last_count = 0

    def handle_delta(delta: str) -> None:
        nonlocal text_buffer, last_count
        text_buffer += delta
        parsed_claims = _extract_complete_claim_objects(text_buffer)
        if len(parsed_claims) <= last_count:
            return

        _set_claims(
            idea_map,
            _merge_claims(list(idea_map.claims or []), parsed_claims),
        )
        idea_map.updated_at = datetime.now(timezone.utc)
        if progress is not None:
            progress.update(len(parsed_claims) - last_count)
            progress.set_postfix(claims=len(parsed_claims))
        last_count = len(parsed_claims)
        db.commit()

    return stream_structured_response(
        system_prompt=IDEA_MAP_CLAIMS_SYSTEM_PROMPT,
        user_prompt=IDEA_MAP_CLAIMS_USER_PROMPT.format(blocks_text=blocks_text),
        response_model=IdeaMapClaimsResponse,
        on_text_delta=handle_delta,
        profile=IDEA_MAP_PROFILE,
    )


def _set_warrant_progress(
    progress: tqdm,
    *,
    valid: int,
    rejected: int,
    failures: int,
) -> None:
    progress.set_postfix(
        valid_warrants=valid,
        rejected_warrants=rejected,
        failures=failures,
    )


def _count_warrants(claims: list[dict] | None) -> int:
    return sum(len(claim.get("warrants", [])) for claim in claims or [])


def _set_claims(idea_map: IdeaMap, claims: list[dict]) -> None:
    idea_map.claims = claims
    flag_modified(idea_map, "claims")


def _stream_warrants_for_claim(
    claim: dict,
    blocks_text: str,
    warrant_queue: Queue[tuple[str, list[dict]]],
) -> dict:
    text_buffer = ""
    last_count = 0

    def handle_delta(delta: str) -> None:
        nonlocal text_buffer, last_count
        text_buffer += delta
        parsed_warrants = _extract_complete_warrant_objects(text_buffer)
        if len(parsed_warrants) <= last_count:
            return

        new_warrants = parsed_warrants[last_count:]
        last_count = len(parsed_warrants)
        warrant_queue.put((claim["id"], new_warrants))

    return stream_structured_response(
        system_prompt=IDEA_MAP_WARRANTS_SYSTEM_PROMPT,
        user_prompt=IDEA_MAP_WARRANTS_USER_PROMPT.format(
            claim_text=claim["text"],
            blocks_text=blocks_text,
        ),
        response_model=IdeaMapWarrantsResponse,
        on_text_delta=handle_delta,
        profile=IDEA_MAP_PROFILE,
    )


def _extract_complete_claim_objects(buffer: str) -> list[dict]:
    return _extract_complete_objects(buffer, "claims", _normalize_claim)


def _extract_complete_warrant_objects(buffer: str) -> list[dict]:
    return _extract_complete_objects(buffer, "warrants", _normalize_warrant)


def _extract_complete_objects(buffer: str, property_name: str, normalize) -> list[dict]:
    decoder = json.JSONDecoder()
    marker = f'"{property_name}"'
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
            normalized = normalize(obj)
            if normalized:
                results.append(normalized)
        idx = next_idx

    return results


def _normalize_claim(raw: dict) -> dict | None:
    try:
        claim = IdeaMapCoreClaim.model_validate(raw).model_dump()
    except Exception:
        return None
    return {
        "id": claim["id"],
        "text": claim["text"],
        "warrants": [],
    }


def _normalize_warrant(
    raw: dict,
    *,
    idea_map_id: str | None = None,
    paper_id: str | None = None,
    claim_id: str | None = None,
) -> dict | None:
    try:
        return IdeaMapWarrant.model_validate(raw).model_dump()
    except Exception as exc:
        logger.warning(
            "idea_map run=%s paper=%s claim=%s dropped_malformed_warrant error=%s raw=%s",
            idea_map_id or "",
            paper_id or "",
            claim_id or "",
            str(exc),
            _json_preview(raw),
        )
        return None


def _json_preview(value: object, limit: int = 2000) -> str:
    try:
        text = json.dumps(value, ensure_ascii=True)
    except TypeError:
        text = str(value)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _merge_claims(existing: list[dict], incoming: list[dict]) -> list[dict]:
    merged = list(existing)
    by_id = {claim.get("id"): claim for claim in merged if claim.get("id")}

    for item in incoming:
        item_id = item.get("id")
        if not item_id:
            continue
        if item_id in by_id:
            by_id[item_id]["text"] = item.get("text", by_id[item_id].get("text", ""))
            by_id[item_id].setdefault("warrants", [])
            continue
        item.setdefault("warrants", [])
        by_id[item_id] = item
        merged.append(item)

    return merged


def _persist_warrants(
    db,
    idea_map: IdeaMap,
    blocks,
    block_map,
    claim_id: str,
    warrants: list[dict],
    rejected_warrant_keys: set[tuple[str, str]],
) -> int:
    if not warrants:
        return 0

    claims = list(idea_map.claims or [])
    target_claim = next((claim for claim in claims if claim.get("id") == claim_id), None)
    if not target_claim:
        return 0

    existing_warrant_ids = {
        warrant.get("id")
        for warrant in target_claim.get("warrants", [])
        if warrant.get("id")
    }
    valid_warrants = []
    rejected_count = 0
    for warrant in warrants:
        if warrant.get("id") in existing_warrant_ids:
            continue
        citation = warrant.get("citation", {})
        diagnostics = citation_validation_diagnostics(blocks, citation)
        if diagnostics["valid"]:
            start_block = block_map[citation["startBlockId"]]
            warrant["citation"] = {
                "startBlockId": citation["startBlockId"],
                "endBlockId": citation["endBlockId"],
                "sectionTitle": citation.get("sectionTitle") or start_block.section_title,
            }
            valid_warrants.append(warrant)
        else:
            warrant_id = str(warrant.get("id", ""))
            rejected_key = (claim_id, warrant_id)
            if rejected_key in rejected_warrant_keys:
                continue
            rejected_warrant_keys.add(rejected_key)
            rejected_count += 1
            logger.warning(
                "idea_map run=%s paper=%s rejected_citation=%s",
                idea_map.id,
                idea_map.paper_id,
                json.dumps(
                    {
                        "claimId": claim_id,
                        "claimText": _preview(target_claim.get("text", "")),
                        "warrantId": warrant_id,
                        "warrantText": _preview(warrant.get("text", "")),
                        "diagnostics": diagnostics,
                    },
                    ensure_ascii=True,
                ),
            )

    if not valid_warrants:
        return rejected_count

    target_claim["warrants"] = _merge_warrants(
        list(target_claim.get("warrants", [])),
        valid_warrants,
    )
    _set_claims(idea_map, claims)
    idea_map.updated_at = datetime.now(timezone.utc)
    db.commit()
    return rejected_count


def _merge_warrants(existing: list[dict], incoming: list[dict]) -> list[dict]:
    merged = list(existing)
    by_id = {warrant.get("id"): warrant for warrant in merged if warrant.get("id")}

    for item in incoming:
        item_id = item.get("id")
        if not item_id:
            continue
        if item_id in by_id:
            by_id[item_id].update(item)
            continue
        by_id[item_id] = item
        merged.append(item)

    return merged
