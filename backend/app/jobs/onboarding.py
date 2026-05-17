"""Onboarding extraction worker job."""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.onboarding_extraction import OnboardingExtraction
from app.llm.client import call_llm, build_json_schema
from app.llm.prompts import (
    ONBOARDING_SYSTEM_PROMPT,
    ONBOARDING_USER_PROMPT,
    ONBOARDING_SCHEMA,
)


DEMO_PROPOSED_FILTERS = [
    {
        "id": "demo-filter-1",
        "name": "Mechanistic Interpretability Progress",
        "rationale": "Track new methods and findings in mechanistic interpretability of neural networks.",
        "definition": {
            "name": "Mechanistic Interpretability Progress",
            "statement": "New techniques or findings that advance mechanistic interpretability of language models",
            "description": "Search for papers presenting novel methods for understanding internal representations and computations in transformer models.",
            "search": {
                "instructions": "Look for papers that present new interpretability methods, circuit analysis, or feature identification techniques for neural networks, especially transformers.",
                "outputMode": "warrants",
            },
        },
    },
    {
        "id": "demo-filter-2",
        "name": "Scaling Laws Evidence",
        "rationale": "Monitor evidence for or against established scaling laws.",
        "definition": {
            "name": "Scaling Laws Evidence",
            "statement": "Evidence that supports, refutes, or complicates known scaling laws for language models",
            "description": "Track papers with empirical results about how model performance scales with compute, data, or parameters.",
            "search": {
                "instructions": "Find papers with empirical scaling experiments that confirm, challenge, or extend known scaling law predictions.",
                "outputMode": "warrants",
            },
        },
    },
    {
        "id": "demo-filter-3",
        "name": "RLHF Alternatives",
        "rationale": "Track developments in alignment methods beyond standard RLHF.",
        "definition": {
            "name": "RLHF Alternatives",
            "statement": "What are the most promising alternatives to RLHF for aligning language models?",
            "description": "Search for papers proposing or evaluating alternatives to reinforcement learning from human feedback.",
            "search": {
                "instructions": "Find papers that propose, evaluate, or compare methods for aligning language models that do not rely on traditional RLHF pipelines with reward models.",
                "outputMode": "answers",
            },
        },
    },
    {
        "id": "demo-filter-4",
        "name": "Emergent Capabilities",
        "rationale": "Monitor discoveries of new emergent capabilities in large models.",
        "definition": {
            "name": "Emergent Capabilities",
            "statement": "What new emergent capabilities have been discovered in large language models?",
            "description": "Track papers documenting capabilities that appear at scale.",
            "search": {
                "instructions": "Find papers that document or analyze capabilities that emerge in language models at sufficient scale, including both beneficial and potentially dangerous ones.",
                "outputMode": "answers",
            },
        },
    },
    {
        "id": "demo-filter-5",
        "name": "AI Safety Research",
        "rationale": "Stay informed about the broader AI safety research landscape.",
        "definition": {
            "name": "AI Safety Research",
            "statement": "AI safety and alignment research",
            "description": "Broadly track papers related to making AI systems safe and aligned with human values.",
            "search": {
                "instructions": "Find papers related to AI safety, including alignment techniques, evaluation of model risks, robustness, and value alignment approaches.",
                "outputMode": "relevance",
            },
        },
    },
]


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

        if not settings.OPENROUTER_API_KEY:
            extraction.proposed_filters = DEMO_PROPOSED_FILTERS
            extraction.status = "completed"
            extraction.completed_at = datetime.now(timezone.utc)
            extraction.updated_at = datetime.now(timezone.utc)
            db.commit()
            return

        user_prompt = ONBOARDING_USER_PROMPT.format(input_text=extraction.input_text)
        response_format = build_json_schema("onboarding_extraction", ONBOARDING_SCHEMA)

        result = call_llm(
            system_prompt=ONBOARDING_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            response_format=response_format,
        )

        content = result["content"]
        proposed = content.get("proposedFilters", [])

        for f in proposed:
            if "id" not in f:
                f["id"] = str(uuid.uuid4())

        extraction.proposed_filters = proposed
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
