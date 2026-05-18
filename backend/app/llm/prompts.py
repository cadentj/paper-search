"""LLM prompt templates and schemas for structured outputs."""

ONBOARDING_SYSTEM_PROMPT = """You are an expert research assistant. Given a researcher's description of their interests, hypotheses, and questions, you will generate targeted search filters.

Each filter should be one of three types:
- Claim filter (mode: "warrants"): Search for evidence supporting or refuting a specific proposition.
- Question filter (mode: "answers"): Search for papers that answer or partially answer a research question.
- Topic filter (mode: "relevance"): Search for papers relevant to a broad research topic.

Generate 2-4 warrant-search filters, 2-3 answer-search filters, and 1-3 relevance-search filters.
Prefer fewer high-quality filters over a long list. Each filter should be specific enough to surface genuinely useful papers."""

ONBOARDING_USER_PROMPT = """Here are the researcher's interests and notes:

{input_text}

Generate proposed search filters based on these interests. For each filter provide:
- id: a unique string identifier
- name: short descriptive name
- description: the claim, question, or topic to search for
- mode: "warrants", "answers", or "relevance"."""

ONBOARDING_SCHEMA = {
    "type": "object",
    "properties": {
        "proposedFilters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "mode": {
                        "type": "string",
                        "enum": ["warrants", "answers", "relevance"],
                    },
                },
                "required": ["id", "name", "description", "mode"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["proposedFilters"],
    "additionalProperties": False,
}

FILTER_SEARCH_SYSTEM_PROMPT = """You are a research paper evaluator. Given a search filter and a list of paper abstracts, evaluate each paper against the filter.

For each paper, determine:
- stance: "supports", "refutes", "complicates", "relevant", or "irrelevant"
- relevanceScore: 0.0 to 1.0 (how relevant to the filter)
- confidence: 0.0 to 1.0 (how confident you are in your assessment)
- rationale: brief explanation of why this paper matches or doesn't match
- matchedClaims: list of specific claims from the paper that relate to the filter
- abstractEvidence: list of quoted evidence from the abstract

Be selective. Most papers should be "irrelevant" unless they genuinely relate to the filter's description and search behavior."""

FILTER_SEARCH_USER_PROMPT = """Filter:
Name: {filter_name}
Description: {filter_description}
Search Behavior: {filter_behavior}

Papers to evaluate:
{papers_text}

Evaluate each paper against this filter."""

FILTER_SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "matches": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "arxivId": {"type": "string"},
                    "stance": {
                        "type": "string",
                        "enum": ["supports", "refutes", "complicates", "relevant", "irrelevant"],
                    },
                    "relevanceScore": {"type": "number"},
                    "confidence": {"type": "number"},
                    "rationale": {"type": "string"},
                    "matchedClaims": {"type": "array", "items": {"type": "string"}},
                    "abstractEvidence": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "arxivId", "stance", "relevanceScore", "confidence",
                    "rationale", "matchedClaims", "abstractEvidence",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["matches"],
    "additionalProperties": False,
}

SUMMARY_SYSTEM_PROMPT = """You are a research digest writer. Given a set of paper matches from a daily search, write a concise cited summary highlighting the most interesting findings.

The summary should:
- Be 2-4 paragraphs
- Cite specific papers using their arXiv IDs
- Focus on what a researcher would find most actionable or surprising
- Group related findings when possible"""

SUMMARY_USER_PROMPT = """Here are the paper matches from today's search:

{matches_text}

Write a concise Daily summary with citations."""

SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "paperMatchId": {"type": "string"},
                    "arxivId": {"type": "string"},
                    "citedFor": {"type": "string"},
                },
                "required": ["paperMatchId", "arxivId", "citedFor"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "citations"],
    "additionalProperties": False,
}

IDEA_MAP_SYSTEM_PROMPT = """You are a paper analyst. Given addressable HTML blocks from the main body of an academic paper, extract the paper's core claims and their supporting warrants with block-range citations.

Definitions:
- Claim: a concise proposition the paper argues, demonstrates, or relies on.
- Warrant: the specific reason the paper gives for believing the claim (a result, experiment, theorem, ablation, argument, or comparison).
- Citation: a contiguous range of provided block ids that justifies the warrant.

Rules:
- Each warrant must have exactly one citation.
- If a warrant needs multiple citations, split it into multiple warrants under the same claim.
- Cite only block ids that appear in the provided content.
- Use startBlockId and endBlockId. For one-block citations, set them to the same id.
- Citation ranges must be contiguous and no longer than 3 blocks.
- Do not invent quotes or cite text that is not supported by the cited block range.
- Include the sectionTitle if the block is within a section."""

IDEA_MAP_USER_PROMPT = """Here are the addressable blocks from the paper HTML:

{blocks_text}

Extract the paper's core claims and supporting warrants with citations to these block ids."""

IDEA_MAP_SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "text": {"type": "string"},
                    "warrants": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "text": {"type": "string"},
                                "citation": {
                                    "type": "object",
                                    "properties": {
                                        "startBlockId": {"type": "string"},
                                        "endBlockId": {"type": "string"},
                                        "sectionTitle": {"type": "string"},
                                    },
                                    "required": ["startBlockId", "endBlockId", "sectionTitle"],
                                    "additionalProperties": False,
                                },
                            },
                            "required": ["id", "text", "citation"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["id", "text", "warrants"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["claims"],
    "additionalProperties": False,
}
