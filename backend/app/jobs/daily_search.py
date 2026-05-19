"""Daily search worker job."""

import asyncio
import logging

from sqlalchemy.orm import Session

from app.config import LLM_MAX_CONCURRENCY
from paper_search_core.models.paper import SQLAPaper
from app.models.paper_match import SQLAPaperMatch
from app.models.search_run import SQLASearchRun
from app.models.job import SQLAJob
from app.services import filters as filter_service
from app.services.settings import enabled_source_types
from app.services.papers_fts import select_daily_search_pairs
from app.services.jobs import set_job_status
from app.services.sources import papers_for_sources
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
from tqdm import tqdm

logger = logging.getLogger(__name__)
PAIR_TIMEOUT_SECONDS = 30.0
PAIRING_PHASE_TIMEOUT_SECONDS = 360.0
PAIR_EVALUATION_FAILED = "evaluation failed"

PairOutcome = tuple[dict | None, str | None, str | None, str | None]


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
    filter: FilterPayload,
    paper: PaperPayload,
) -> PairOutcome:
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

    return result, None, llm_result["model"], llm_result["response_id"]


async def _evaluate_filter_paper_with_timeout(
    semaphore: asyncio.Semaphore,
    filter: FilterPayload,
    paper: PaperPayload,
) -> PairOutcome:
    async with semaphore:
        try:
            return await asyncio.wait_for(
                _evaluate_filter_paper(filter=filter, paper=paper),
                timeout=PAIR_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            return None, f"{PAIR_EVALUATION_FAILED}: timed out", None, None
        except Exception as exc:
            return None, f"{PAIR_EVALUATION_FAILED}: {exc}", None, None


async def _evaluate_pairs(
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
            filter, paper = task_pairs[task]
            await on_result(filter, paper, await task)

    if pending:
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for task in pending:
            filter, paper = task_pairs[task]
            await on_result(
                filter,
                paper,
                (None, PAIR_EVALUATION_FAILED, None, None),
            )


def run(db: Session, job: SQLAJob) -> None:
    """Evaluate filters against daily papers and persist matches."""
    from app.services import search_runs

    search_run_id = job.subject_id
    if not search_run_id:
        return

    run = db.query(SQLASearchRun).filter(SQLASearchRun.id == search_run_id).first()
    if not run:
        return

    try:
        search_runs.mark_running(db, run, job)

        papers = papers_for_sources(db, enabled_source_types(db), run.run_date)

        active_filters = filter_service.list_filters(db, status="active")
        filter_payloads = [f.to_search_payload() for f in active_filters]
        papers_by_id = {p.id: p.to_search_payload() for p in papers}

        search_runs.update_candidate_counts(
            db,
            run,
            candidate_count=len(papers),
            candidate_counts=_candidate_counts_by_source(papers),
        )

        if not filter_payloads or not papers:
            run.match_count = 0
            set_job_status(job, status="completed")
            db.commit()
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
            db.commit()
            run.match_count = 0
            set_job_status(job, status="completed")
            db.commit()
            return

        search_runs.set_pair_progress(db, job, total=pair_total)

        completed_pairs = 0
        failed_pairs = 0
        first_pair_error = ""

        async def handle_pair_result(
            filter: FilterPayload,
            paper: PaperPayload,
            outcome: PairOutcome,
        ) -> None:
            nonlocal completed_pairs, failed_pairs, first_pair_error
            completed_pairs += 1

            result, error, llm_model, llm_response_id = outcome
            if error:
                failed_pairs += 1
                if not first_pair_error:
                    first_pair_error = error
                tqdm.write(
                    f"Pair {completed_pairs}/{pair_total} failed: "
                    f"{filter.name} x {paper.item_id}"
                )
            elif result and result.get("reason", "").strip():
                db.add(
                    SQLAPaperMatch(
                        search_run_id=search_run_id,
                        filter_id=filter.id,
                        paper_id=paper.id,
                        result=result,
                        llm_model=llm_model,
                        llm_response_id=llm_response_id,
                    )
                )
            job.progress = {"current": completed_pairs, "total": pair_total}
            db.commit()
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
        run.match_count = match_count
        set_job_status(job, status="completed")
        db.commit()

    except Exception as e:
        db.rollback()
        run = db.query(SQLASearchRun).filter(SQLASearchRun.id == search_run_id).first()
        if run:
            search_runs.fail_run(db, run, job, str(e))
        logger.exception("daily_search run=%s failed", search_run_id)
        raise
