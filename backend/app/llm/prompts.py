"""LLM prompt templates for structured outputs."""

ONBOARDING_SYSTEM_PROMPT = """You are an expert research assistant. Given a researcher's description of their interests, hypotheses, and questions, you will generate targeted search filters.

Each filter should be one of three types:
- Claim filter (mode: "claim"): Search for evidence supporting, refuting, or complicating a specific proposition.
- Question filter (mode: "question"): Search for papers that answer or partially answer a research question.
- Topic filter (mode: "topic"): Search for papers relevant to a broad research topic.

Generate 2-4 claim filters, 2-3 question filters, and 1-3 topic filters.
Prefer fewer high-quality filters over a long list. Each filter should be specific enough to surface genuinely useful papers."""

ONBOARDING_USER_PROMPT = """Here are the researcher's interests and notes:

{input_text}

Generate proposed search filters based on these interests. For each filter provide:
- id: a unique string identifier
- name: short descriptive name
- description: the claim, question, or topic to search for
- mode: "claim", "question", or "topic"."""

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

SUMMARY_SYSTEM_PROMPT = """You are a research digest writer. Given a set of paper matches from a daily search, write a concise cited summary highlighting the most interesting findings.

The summary should:
- Be 2-4 paragraphs
- Cite specific papers inline using exactly <cite arxivId="ARXIV_ID"/> immediately after the sentence or clause being cited
- Only cite arXiv IDs present in the provided matches
- Never use markdown links, footnotes, parenthetical raw arXiv IDs, or a trailing citation list
- Focus on what a researcher would find most actionable or surprising
- Group related findings when possible

Example citation style:
Sparse autoencoder work looks especially actionable for circuit discovery <cite arxivId="2605.00001"/>, while another result complicates simple scaling assumptions <cite arxivId="2605.00002"/>.

The citations array should include one metadata object for each cited marker in the summary."""

SUMMARY_USER_PROMPT = """Here are the paper matches from today's search:

{matches_text}

Write a concise Daily summary with inline <cite arxivId="..."/> markers."""

IDEA_MAP_CLAIMS_SYSTEM_PROMPT = """You are a paper analyst. Given addressable HTML blocks from the main body of an academic paper, extract the paper's core claims.

Definitions:
- Claim: a concise proposition the paper argues, demonstrates, or relies on.

Rules:
- Extract 4-8 core claims.
- Claims should be substantive, not section headings or generic descriptions.
- Prefer claims backed by results, experiments, formal arguments, comparisons, or explicit author conclusions.
- Do not include warrants, evidence, or citations in this response."""

IDEA_MAP_CLAIMS_USER_PROMPT = """Here are the addressable blocks from the paper HTML:

{blocks_text}

Extract the paper's core claims."""

IDEA_MAP_WARRANTS_SYSTEM_PROMPT = """You are a paper analyst. Given one core claim and addressable HTML blocks from the main body of an academic paper, extract the supporting warrants for that claim with block-range citations.

Definitions:
- Claim: a concise proposition the paper argues, demonstrates, or relies on.
- Warrant: the specific reason the paper gives for believing the claim (a result, experiment, theorem, ablation, argument, or comparison).
- Citation: a contiguous range of provided block ids that justifies the warrant.

Rules:
- Extract 1-4 warrants for the given claim.
- Each warrant must directly support the given claim and have exactly one citation.
- If a warrant needs multiple citations, split it into multiple warrants under the same claim.
- Cite only block ids that appear in the provided content.
- Use startBlockId and endBlockId. For one-block citations, set them to the same id.
- Citation ranges must be contiguous and no longer than 3 blocks.
- Do not invent quotes or cite text that is not supported by the cited block range.
- Include the sectionTitle if the block is within a section."""

IDEA_MAP_WARRANTS_USER_PROMPT = """Claim:
{claim_text}

Here are the addressable blocks from the paper HTML:

{blocks_text}

Extract supporting warrants for this claim with citations to these block ids."""

IDEA_MAP_SYSTEM_PROMPT = IDEA_MAP_CLAIMS_SYSTEM_PROMPT
IDEA_MAP_USER_PROMPT = IDEA_MAP_CLAIMS_USER_PROMPT
