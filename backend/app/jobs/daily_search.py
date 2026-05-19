"""Daily search worker job."""

import asyncio
import logging

from app.core.config import LLM_MAX_CONCURRENCY
from app.db.session import database
from paper_search_core.models.paper import SQLAPaper
from app.models.paper_match import SQLAPaperMatch
from app.models.search_run import SQLASearchRun
from app.models.job import SQLAJob
from app.services import filters as filter_service
from app.services.papers_fts import select_daily_search_pairs
from app.services.sources import enabled_source_types, papers_for_sources
from app.llm.client import async_call_llm
from app.llm.config import JUDGE_PROFILE
from app.llm.prompts import (
    CLAIM_FILTER_SEARCH_SYSTEM_PROMPT,
    CLAIM_FILTER_SEARCH_USER_PROMPT,
    TOPIC_FILTER_SEARCH_SYSTEM_PROMPT,
    TOPIC_FILTER_SEARCH_USER_PROMPT,
)
from app.llm.schemas import ClaimFilterSearchResponse, TopicFilterSearchResponse
from app.models.filter import FilterPayload
from paper_search_core.schemas.daily_search import PaperPayload
from pydantic import BaseModel
from tqdm import tqdm

logger = logging.getLogger(__name__)
PAIR_TIMEOUT_SECONDS = 30.0
PAIRING_PHASE_TIMEOUT_SECONDS = 360.0


class PairEvaluation(BaseModel):
    filter_id: str
    filter_name: str
    paper_id: str
    paper_title: str
    source_type: str
    source_id: str
    item_id: str
    result: dict | None = None
    model: str | None = None
    response_id: str | None = None
    error: str | None = None


def _candidate_counts_by_source(papers: list[SQLAPaper]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for paper in papers:
        source_type = paper.source_type or "arxiv"
        counts[source_type] = counts.get(source_type, 0) + 1
    return counts


def _prompts_for_mode(mode: str):
    if mode == "claim":
        return (
            CLAIM_FILTER_SEARCH_SYSTEM_PROMPT,
            CLAIM_FILTER_SEARCH_USER_PROMPT,
            ClaimFilterSearchResponse,
        )
    return (
        TOPIC_FILTER_SEARCH_SYSTEM_PROMPT,
        TOPIC_FILTER_SEARCH_USER_PROMPT,
        TopicFilterSearchResponse,
    )


def _extract_result(mode: str, match: dict | None) -> dict | None:
    if not match:
        return None
    if mode == "claim":
        return {
            "verdict": match.get("verdict", "positive"),
            "reason": match.get("reason", ""),
            "evidence": match.get("evidence"),
        }
    return {"reason": match.get("reason", ""), "evidence": match.get("evidence")}


async def _evaluate_filter_paper(
    *,
    filter: FilterPayload,
    paper: PaperPayload,
) -> PairEvaluation:
    definition = filter.definition or {}
    mode = definition.get("mode", "topic")
    system_prompt, user_prompt_template, response_model = _prompts_for_mode(mode)

    user_prompt = user_prompt_template.format(
        filter_name=definition.get("name", filter.name),
        filter_description=definition.get("description", ""),
        papers_text=paper.prompt_text(),
    )
    llm_result = await async_call_llm(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        response_model=response_model,
        profile=JUDGE_PROFILE,
    )

    matches = llm_result["content"].get("matches", [])
    raw_match = next(
        (m for m in matches if m.get("itemId") == paper.item_id),
        matches[0] if matches else None,
    )
    result = _extract_result(mode, raw_match)

    return PairEvaluation(
        filter_id=filter.id,
        filter_name=filter.name,
        paper_id=paper.id,
        paper_title=paper.title,
        source_type=paper.source_type,
        source_id=paper.source_id,
        item_id=paper.item_id,
        result=result,
        model=llm_result["model"],
        response_id=llm_result["response_id"],
    )


def _pair_error_evaluation(
    *,
    filter: FilterPayload,
    paper: PaperPayload,
    error: str,
) -> PairEvaluation:
    return PairEvaluation(
        filter_id=filter.id,
        filter_name=filter.name,
        paper_id=paper.id,
        paper_title=paper.title,
        source_type=paper.source_type or "arxiv",
        source_id=paper.source_id or "",
        item_id=paper.item_id,
        error=error,
    )


async def _evaluate_filter_paper_with_timeout(
    *,
    semaphore: asyncio.Semaphore,
    filter: FilterPayload,
    paper: PaperPayload,
) -> PairEvaluation:
    async with semaphore:
        try:
            return await asyncio.wait_for(
                _evaluate_filter_paper(filter=filter, paper=paper),
                timeout=PAIR_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            return _pair_error_evaluation(
                filter=filter,
                paper=paper,
                error=f"Timed out after {PAIR_TIMEOUT_SECONDS:g}s",
            )
        except Exception as exc:
            return _pair_error_evaluation(
                filter=filter,
                paper=paper,
                error=str(exc),
            )


async def _evaluate_pairs(
    *,
    pairs: list[tuple[FilterPayload, PaperPayload]],
    on_result,
) -> None:
    semaphore = asyncio.Semaphore(max(LLM_MAX_CONCURRENCY, 1))
    task_pairs = {}
    for filter, paper in pairs:
        task = asyncio.create_task(
            _evaluate_filter_paper_with_timeout(
                semaphore=semaphore,
                filter=filter,
                paper=paper,
            )
        )
        task_pairs[task] = (filter, paper)

    pending = set(task_pairs)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + PAIRING_PHASE_TIMEOUT_SECONDS

    while pending:
        remaining = max(deadline - loop.time(), 0)
        if remaining <= 0:
            break
        done, pending = await asyncio.wait(
            pending,
            timeout=remaining,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if not done:
            break
        for task in done:
            await on_result(await task)

    if pending:
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for task in pending:
            filter, paper = task_pairs[task]
            await on_result(
                PairEvaluation(
                    filter_id=filter.id,
                    filter_name=filter.name,
                    paper_id=paper.id,
                    paper_title=paper.title,
                    source_type=paper.source_type,
                    source_id=paper.source_id,
                    item_id=paper.item_id,
                    error=f"Pairing phase timed out after {PAIRING_PHASE_TIMEOUT_SECONDS:g}s",
                )
            )


def run_daily_search(search_run_id: str, job_id: str) -> None:
    """Worker job: evaluate filters against daily papers and persist matches."""
    from app.services import search_runs

    with database.session() as db:
        run = db.query(SQLASearchRun).filter(SQLASearchRun.id == search_run_id).first()
        if not run:
            return

        job = db.query(SQLAJob).filter(SQLAJob.id == job_id).first()
        if not job:
            return

        try:
            search_runs.mark_running(db, run, job)

            papers = papers_for_sources(db, enabled_source_types(db), run.run_date)

            active_filters = filter_service.list_active_filters(db)
            filter_payloads = [f.to_search_payload() for f in active_filters]
            papers_by_id = {p.id: p.to_search_payload() for p in papers}

            search_runs.update_candidate_counts(
                db,
                run,
                candidate_count=len(papers),
                candidate_counts=_candidate_counts_by_source(papers),
            )

            if not filter_payloads or not papers:
                search_runs.set_match_count(db, run, 0)
                search_runs.complete_daily_search_job(db, job)
                return

            candidate_pairs = select_daily_search_pairs(
                db,
                filters=filter_payloads,
                papers_by_id=papers_by_id,
                run_date=run.run_date,
            )
            pair_total = len(candidate_pairs)

            if pair_total == 0:
                job.progress = {"current": 0, "total": 0}
                search_runs.commit_progress(db)
                search_runs.set_match_count(db, run, 0)
                search_runs.complete_daily_search_job(db, job)
                return

            search_runs.set_pair_progress(db, job, total=pair_total)

            completed_pairs = 0
            failed_pairs = 0
            first_pair_error = ""

            async def handle_pair_result(evaluation: PairEvaluation) -> None:
                nonlocal completed_pairs, failed_pairs, first_pair_error
                completed_pairs += 1

                if evaluation.error:
                    failed_pairs += 1
                    if not first_pair_error:
                        first_pair_error = evaluation.error
                    tqdm.write(
                        f"Pair {completed_pairs}/{pair_total} failed: "
                        f"{evaluation.filter_name} x {evaluation.item_id}: "
                        f"{evaluation.error}"
                    )
                else:
                    result = evaluation.result
                    has_content = result and result.get("reason", "").strip()
                    if has_content:
                        db.add(
                            SQLAPaperMatch(
                                search_run_id=search_run_id,
                                filter_id=evaluation.filter_id,
                                paper_id=evaluation.paper_id,
                                result=result,
                                llm_model=evaluation.model,
                                llm_response_id=evaluation.response_id,
                            )
                        )
                job.progress = {"current": completed_pairs, "total": pair_total}
                search_runs.commit_progress(db)
                pair_progress.update(1)

            with tqdm(
                total=pair_total,
                desc="filter-item pairs",
                unit="pair",
                dynamic_ncols=True,
                disable=None,
            ) as pair_progress:
                asyncio.run(
                    _evaluate_pairs(
                        pairs=candidate_pairs,
                        on_result=handle_pair_result,
                    )
                )

            if failed_pairs == pair_total:
                raise RuntimeError(
                    f"All {pair_total} filter-item evaluations failed. First error: {first_pair_error}"
                )

            match_count = (
                db.query(SQLAPaperMatch)
                .filter(SQLAPaperMatch.search_run_id == search_run_id)
                .count()
            )
            search_runs.set_match_count(db, run, match_count)
            search_runs.complete_daily_search_job(db, job)

        except Exception as e:
            db.rollback()
            run = (
                db.query(SQLASearchRun)
                .filter(SQLASearchRun.id == search_run_id)
                .first()
            )
            if run:
                job = search_runs.resolve_daily_search_job(db, search_run_id, job_id)
                search_runs.fail_run(db, run, job, str(e))
            logger.exception("daily_search run=%s failed", search_run_id)
            raise
