"""Idea map generation worker job."""

import hashlib
import json
import logging
from datetime import datetime, timezone

import httpx

from app.db.session import SessionLocal
from app.models.paper import Paper
from app.models.paper_html import PaperHtml
from app.models.idea_map import IdeaMap
from app.services.html_parser import (
    blocks_to_prompt_text,
    citation_validation_diagnostics,
    parse_arxiv_html,
)
from app.llm.client import call_llm, build_json_schema
from app.llm.prompts import (
    IDEA_MAP_SYSTEM_PROMPT,
    IDEA_MAP_USER_PROMPT,
    IDEA_MAP_SCHEMA,
)


logger = logging.getLogger(__name__)


def generate_idea_map(idea_map_id: str) -> None:
    """Worker job: generate idea map from arXiv HTML."""
    db = SessionLocal()
    try:
        idea_map = db.query(IdeaMap).filter(IdeaMap.id == idea_map_id).first()
        if not idea_map:
            return

        idea_map.status = "running"
        idea_map.updated_at = datetime.now(timezone.utc)
        db.commit()

        paper = db.query(Paper).filter(Paper.id == idea_map.paper_id).first()
        if not paper or not paper.arxiv_id:
            idea_map.status = "skipped"
            idea_map.dropped_reason = "Paper not found or missing arxiv_id"
            idea_map.updated_at = datetime.now(timezone.utc)
            db.commit()
            return

        html_url = f"https://arxiv.org/html/{paper.arxiv_id}"
        idea_map.source_url = html_url

        cached = db.query(PaperHtml).filter(PaperHtml.paper_id == paper.id).first()

        if cached:
            html_content = cached.html
        else:
            try:
                with httpx.Client(timeout=30.0, follow_redirects=True) as client:
                    resp = client.get(html_url)
                    resp.raise_for_status()
                    html_content = resp.text
            except Exception:
                idea_map.status = "skipped"
                idea_map.dropped_reason = f"Could not fetch HTML from {html_url}"
                idea_map.updated_at = datetime.now(timezone.utc)
                db.commit()
                return

            content_hash = hashlib.sha256(html_content.encode()).hexdigest()
            paper_html = PaperHtml(
                paper_id=paper.id,
                source_url=html_url,
                html=html_content,
                content_hash=content_hash,
                fetched_at=datetime.now(timezone.utc),
            )
            db.add(paper_html)
            db.commit()

        blocks = parse_arxiv_html(html_content)
        if not blocks:
            idea_map.status = "skipped"
            idea_map.dropped_reason = "HTML could not be parsed into addressable blocks"
            idea_map.updated_at = datetime.now(timezone.utc)
            db.commit()
            return

        blocks_text = blocks_to_prompt_text(blocks)
        user_prompt = IDEA_MAP_USER_PROMPT.format(blocks_text=blocks_text)
        response_format = build_json_schema("idea_map", IDEA_MAP_SCHEMA)

        result = call_llm(
            system_prompt=IDEA_MAP_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_format=response_format,
        )

        content = result["content"]
        raw_claims = content.get("claims", [])
        raw_warrant_count = sum(len(claim.get("warrants", [])) for claim in raw_claims)
        logger.info(
            "idea_map run=%s paper=%s arxiv=%s raw_claims=%s raw_warrants=%s blocks=%s",
            idea_map.id,
            paper.id,
            paper.arxiv_id,
            len(raw_claims),
            raw_warrant_count,
            len(blocks),
        )

        validated_claims = []
        rejected_warrant_count = 0
        for claim in raw_claims:
            valid_warrants = []
            for warrant in claim.get("warrants", []):
                citation = warrant.get("citation", {})
                diagnostics = citation_validation_diagnostics(blocks, citation)
                if diagnostics["valid"]:
                    valid_warrants.append(warrant)
                else:
                    rejected_warrant_count += 1
                    logger.warning(
                        "idea_map run=%s paper=%s rejected_citation=%s",
                        idea_map.id,
                        paper.id,
                        json.dumps(
                            {
                                "claimId": claim.get("id", ""),
                                "claimText": _preview(claim.get("text", "")),
                                "warrantId": warrant.get("id", ""),
                                "warrantText": _preview(warrant.get("text", "")),
                                "diagnostics": diagnostics,
                            },
                            ensure_ascii=True,
                        ),
                    )
            if valid_warrants:
                claim["warrants"] = valid_warrants
                validated_claims.append(claim)

        logger.info(
            "idea_map run=%s paper=%s validated_claims=%s validated_warrants=%s rejected_warrants=%s",
            idea_map.id,
            paper.id,
            len(validated_claims),
            sum(len(claim.get("warrants", [])) for claim in validated_claims),
            rejected_warrant_count,
        )
        if raw_claims and not validated_claims:
            logger.warning(
                "idea_map run=%s paper=%s all_claims_dropped_after_citation_validation",
                idea_map.id,
                paper.id,
            )

        idea_map.claims = validated_claims
        idea_map.llm_model = result["model"]
        idea_map.llm_response_id = result["response_id"]
        idea_map.status = "completed"
        idea_map.updated_at = datetime.now(timezone.utc)
        db.commit()

    except Exception as e:
        db.rollback()
        idea_map = db.query(IdeaMap).filter(IdeaMap.id == idea_map_id).first()
        if idea_map:
            idea_map.status = "failed"
            idea_map.error = str(e)
            idea_map.updated_at = datetime.now(timezone.utc)
            db.commit()
        raise
    finally:
        db.close()


def _preview(value: object, limit: int = 500) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."
