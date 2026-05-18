"""Daily search worker job."""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.filter import Filter
from app.models.paper import Paper
from app.models.paper_match import PaperMatch
from app.models.search_run import SearchRun
from app.models.feedback import Feedback
from app.llm.client import call_llm, build_json_schema
from app.llm.prompts import (
    FILTER_SEARCH_SYSTEM_PROMPT,
    FILTER_SEARCH_USER_PROMPT,
    FILTER_SEARCH_SCHEMA,
    SUMMARY_SYSTEM_PROMPT,
    SUMMARY_USER_PROMPT,
    SUMMARY_SCHEMA,
)


def _build_papers_text(papers: list[Paper]) -> str:
    lines = []
    for p in papers:
        lines.append(
            f"ArXiv ID: {p.arxiv_id}\n"
            f"Title: {p.title}\n"
            f"Authors: {', '.join(p.authors) if p.authors else 'Unknown'}\n"
            f"Abstract: {p.abstract}\n"
        )
    return "\n---\n".join(lines)


def _build_matches_text(matches: list[dict]) -> str:
    lines = []
    for m in matches:
        lines.append(
            f"Paper: {m.get('paper_title', 'Unknown')} ({m.get('arxiv_id', '')})\n"
            f"Filter: {m.get('filter_name', 'Unknown')}\n"
            f"Stance: {m.get('stance', '')}\n"
            f"Score: {m.get('relevance_score', 0)}\n"
            f"Rationale: {m.get('rationale', '')}\n"
            f"Match ID: {m.get('match_id', '')}\n"
        )
    return "\n---\n".join(lines)


DEMO_MATCHES = {
    "2401.00001": {
        "stance": "relevant",
        "relevanceScore": 0.85,
        "confidence": 0.9,
        "rationale": "This paper directly addresses scaling laws for neural language models with comprehensive empirical analysis.",
        "matchedClaims": ["Predictable power-law relationships in model scaling"],
        "abstractEvidence": ["larger models are significantly more sample-efficient"],
    },
    "2401.00002": {
        "stance": "supports",
        "relevanceScore": 0.92,
        "confidence": 0.88,
        "rationale": "Presents systematic mechanistic interpretability study of transformer attention heads.",
        "matchedClaims": ["Attention heads perform specific computational roles", "Automated tools can classify head behavior"],
        "abstractEvidence": ["certain heads consistently perform induction, copying, or inhibition operations"],
    },
    "2401.00003": {
        "stance": "supports",
        "relevanceScore": 0.88,
        "confidence": 0.85,
        "rationale": "DPO is a direct alternative to RLHF that eliminates the need for reward models.",
        "matchedClaims": ["DPO matches or exceeds RLHF performance"],
        "abstractEvidence": ["directly optimizes the policy using preference data without an explicit reward model"],
    },
    "2401.00004": {
        "stance": "supports",
        "relevanceScore": 0.95,
        "confidence": 0.92,
        "rationale": "Sparse autoencoders reveal interpretable features in language models enabling targeted model steering.",
        "matchedClaims": ["Learned features correspond to interpretable concepts", "Features enable targeted model steering"],
        "abstractEvidence": ["amplifying or suppressing specific features predictably alters model behavior"],
    },
    "2401.00005": {
        "stance": "relevant",
        "relevanceScore": 0.7,
        "confidence": 0.8,
        "rationale": "Chain-of-thought prompting reveals emergent reasoning capabilities at scale.",
        "matchedClaims": ["CoT improves complex reasoning performance"],
        "abstractEvidence": ["this capability emerges at sufficient model scale"],
    },
    "2401.00006": {
        "stance": "relevant",
        "relevanceScore": 0.82,
        "confidence": 0.85,
        "rationale": "Constitutional AI provides an alternative alignment approach using explicit principles.",
        "matchedClaims": ["CAI achieves similar helpfulness with improved harmlessness"],
        "abstractEvidence": ["the principles governing behavior are explicit and auditable"],
    },
}

DEMO_SUMMARY = {
    "summary": (
        "Today's search surfaced several significant papers across interpretability, alignment, and scaling.\n\n"
        "In mechanistic interpretability, two papers stand out. A systematic study of transformer attention heads "
        "(2401.00002) identifies specific computational roles through causal interventions, showing that certain "
        "heads consistently perform induction, copying, or inhibition. Complementing this, sparse autoencoders "
        "(2401.00004) reveal interpretable features that enable targeted model steering without retraining.\n\n"
        "On the alignment front, Direct Preference Optimization (2401.00003) presents a compelling RLHF alternative "
        "that eliminates reward models entirely while matching performance. Constitutional AI (2401.00006) takes "
        "a different approach, using explicit principles to guide self-critique during training.\n\n"
        "Additionally, scaling law analysis (2401.00001) provides evidence that current models are substantially "
        "undertrained, suggesting room for significant efficiency gains in training next-generation models."
    ),
    "citations": [
        {"paperMatchId": "", "arxivId": "2401.00002", "citedFor": "Mechanistic analysis of attention head roles"},
        {"paperMatchId": "", "arxivId": "2401.00004", "citedFor": "Interpretable features via sparse autoencoders"},
        {"paperMatchId": "", "arxivId": "2401.00003", "citedFor": "DPO as RLHF alternative"},
        {"paperMatchId": "", "arxivId": "2401.00006", "citedFor": "Constitutional AI alignment approach"},
        {"paperMatchId": "", "arxivId": "2401.00001", "citedFor": "Evidence that models are undertrained"},
    ],
}


def run_daily_search(search_run_id: str) -> None:
    """Worker job: run daily search across all active filters."""
    db = SessionLocal()
    try:
        run = db.query(SearchRun).filter(SearchRun.id == search_run_id).first()
        if not run:
            return

        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        db.commit()

        active_filters = db.query(Filter).filter(Filter.status == "active").all()
        papers = db.query(Paper).all()

        if not active_filters or not papers:
            run.status = "completed"
            run.candidate_count = len(papers)
            run.match_count = 0
            run.summary = "No active filters or papers to search."
            run.completed_at = datetime.now(timezone.utc)
            db.commit()
            return

        all_match_info = []

        for filt in active_filters:
            if not settings.OPENROUTER_API_KEY:
                for paper in papers:
                    demo_match_data = DEMO_MATCHES.get(paper.arxiv_id)
                    if not demo_match_data:
                        continue

                    match = PaperMatch(
                        id=str(uuid.uuid4()),
                        search_run_id=search_run_id,
                        filter_id=filt.id,
                        paper_id=paper.id,
                        stance=demo_match_data["stance"],
                        relevance_score=demo_match_data["relevanceScore"],
                        confidence=demo_match_data["confidence"],
                        rationale=demo_match_data["rationale"],
                        matched_claims=demo_match_data["matchedClaims"],
                        abstract_evidence=demo_match_data["abstractEvidence"],
                    )
                    db.add(match)
                    all_match_info.append({
                        "match_id": match.id,
                        "paper_title": paper.title,
                        "arxiv_id": paper.arxiv_id,
                        "filter_name": filt.name,
                        "stance": match.stance,
                        "relevance_score": match.relevance_score,
                        "rationale": match.rationale,
                    })
                continue

            definition = filt.definition or {}
            search_config = definition.get("search", {})

            papers_text = _build_papers_text(papers)
            user_prompt = FILTER_SEARCH_USER_PROMPT.format(
                filter_name=definition.get("name", filt.name),
                filter_statement=definition.get("statement", ""),
                filter_instructions=search_config.get("instructions", ""),
                output_mode=search_config.get("outputMode", "relevance"),
                papers_text=papers_text,
            )
            response_format = build_json_schema("filter_search", FILTER_SEARCH_SCHEMA)

            result = call_llm(
                system_prompt=FILTER_SEARCH_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                response_format=response_format,
            )

            content = result["content"]
            matches_data = content.get("matches", [])

            arxiv_to_paper = {p.arxiv_id: p for p in papers}

            for m_data in matches_data:
                paper = arxiv_to_paper.get(m_data.get("arxivId"))
                if not paper:
                    continue

                match = PaperMatch(
                    id=str(uuid.uuid4()),
                    search_run_id=search_run_id,
                    filter_id=filt.id,
                    paper_id=paper.id,
                    stance=m_data.get("stance", "irrelevant"),
                    relevance_score=m_data.get("relevanceScore", 0.0),
                    confidence=m_data.get("confidence"),
                    rationale=m_data.get("rationale", ""),
                    matched_claims=m_data.get("matchedClaims", []),
                    abstract_evidence=m_data.get("abstractEvidence", []),
                    llm_model=result["model"],
                    llm_response_id=result["response_id"],
                )
                db.add(match)
                all_match_info.append({
                    "match_id": match.id,
                    "paper_title": paper.title,
                    "arxiv_id": paper.arxiv_id,
                    "filter_name": filt.name,
                    "stance": match.stance,
                    "relevance_score": match.relevance_score,
                    "rationale": match.rationale,
                })

        db.commit()

        visible_matches = [m for m in all_match_info if m["stance"] != "irrelevant"]
        match_count = len(visible_matches)

        if not settings.OPENROUTER_API_KEY:
            summary_data = DEMO_SUMMARY
            for cit in summary_data["citations"]:
                for m_info in all_match_info:
                    if m_info["arxiv_id"] == cit["arxivId"]:
                        cit["paperMatchId"] = m_info["match_id"]
                        break
        else:
            if visible_matches:
                matches_text = _build_matches_text(visible_matches)
                user_prompt = SUMMARY_USER_PROMPT.format(matches_text=matches_text)
                response_format = build_json_schema("search_summary", SUMMARY_SCHEMA)

                result = call_llm(
                    system_prompt=SUMMARY_SYSTEM_PROMPT,
                    user_prompt=user_prompt,
                    response_format=response_format,
                )
                summary_data = result["content"]
            else:
                summary_data = {
                    "summary": "No relevant papers found in today's search.",
                    "citations": [],
                }

        run.candidate_count = len(papers)
        run.match_count = match_count
        run.summary = summary_data.get("summary", "")
        run.summary_citations = summary_data.get("citations", [])
        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        db.commit()

    except Exception as e:
        db.rollback()
        run = db.query(SearchRun).filter(SearchRun.id == search_run_id).first()
        if run:
            run.status = "failed"
            run.error = str(e)
            db.commit()
        raise
    finally:
        db.close()
