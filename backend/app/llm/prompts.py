"""LLM prompt templates for structured outputs."""

ONBOARDING_SYSTEM_PROMPT = """You are an expert research assistant. Given a researcher's description of their interests, hypotheses, and questions, you will generate targeted search filters.

Each filter should be one of two types:
- Topic filter (mode: "topic"): Search for papers relevant to a research topic or question.
- Claim filter (mode: "claim"): Search for evidence supporting, refuting, or complicating a specific proposition.

Generate 3-5 topic filters and 2-4 claim filters.
Prefer fewer high-quality filters over a long list. Each filter should be specific enough to surface genuinely useful papers."""

ONBOARDING_USER_PROMPT = """Here are the researcher's interests and notes:

{input_text}

Generate proposed search filters based on these interests. For each filter provide:
- id: a unique string identifier
- name: short descriptive name
- description: the claim, question, or topic to search for
- mode: "claim" or "topic"."""

ONBOARDING_WITH_DOCUMENTS_USER_PROMPT = """Here are the researcher's current notes:

{input_text}

Here are summaries of uploaded context documents:

{document_summaries}

Generate proposed search filters based on these notes and document summaries. For each filter provide:
- id: a unique string identifier
- name: short descriptive name
- description: the claim, question, or topic to search for
- mode: "claim" or "topic"."""

DOCUMENT_SUMMARY_SYSTEM_PROMPT = """You summarize research documents for a researcher configuring search filters.

Write a compact summary focused on:
- research questions, hypotheses, claims, methods, and topics the user may want to follow
- distinctive terminology that should influence future search filters
- what kind of papers or research items would be relevant next

Do not critique the document. Do not include markdown."""

DOCUMENT_SUMMARY_USER_PROMPT = """Document title: {filename}

Extracted text:

{document_text}

Write a concise summary for generating future research search filters."""

FILTER_SEARCH_SYSTEM_PROMPT = """You are a research item evaluator. Given a search filter and research items, evaluate each item.

For each item, return:
- itemId, sourceType, sourceId: exact values from the input
- result: 1-2 sentences explaining how the item relates to the filter, following the Search Behavior in the user prompt. Include specific evidence from the excerpt when relevant. Return an empty string if the item does not genuinely relate.

Be selective. Most items should have an empty result."""

FILTER_SEARCH_USER_PROMPT = """Filter:
Name: {filter_name}
Description: {filter_description}
Search Behavior: {filter_behavior}

Items to evaluate:
{papers_text}

Evaluate each item against this filter."""

SUMMARY_SYSTEM_PROMPT = """You are a research digest writer. Given a set of item matches from a daily search, write a concise cited summary highlighting the most interesting findings.

The summary should:
- Be 2-4 paragraphs
- Cite specific items inline using exactly <cite itemId="ITEM_ID"/> immediately after the sentence or clause being cited
- Only cite item IDs present in the provided matches
- Never use markdown links, footnotes, parenthetical raw IDs, or a trailing citation list
- Focus on what a researcher would find most actionable or surprising
- Group related findings when possible

Example citation style:
Sparse autoencoder work looks especially actionable for circuit discovery <cite itemId="arxiv:2605.00001"/>, while a LessWrong post raises a practical caveat <cite itemId="lesswrong:abc123"/>.

The citations array should include one metadata object for each cited marker in the summary."""

SUMMARY_USER_PROMPT = """Here are the item matches from today's search:

{matches_text}

Write a concise Daily summary with inline <cite itemId="..."/> markers."""

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
- Cite only canonical block ids that appear in square brackets in the provided content, such as B014.
- Use startBlockId and endBlockId. For one-block citations, set them to the same id.
- Citation ranges must be contiguous and no longer than 3 blocks.
- Do not invent numeric ranges or derive ids from position. The only valid ids are the exact bracketed ids shown in the content.
- Do not invent quotes or cite text that is not supported by the cited block range.
- Include the sectionTitle if the block is within a section."""

IDEA_MAP_WARRANTS_USER_PROMPT = """Claim:
{claim_text}

Here are the addressable blocks from the paper HTML:

{blocks_text}

Extract supporting warrants for this claim with citations to these block ids."""

IDEA_MAP_SYSTEM_PROMPT = IDEA_MAP_CLAIMS_SYSTEM_PROMPT
IDEA_MAP_USER_PROMPT = IDEA_MAP_CLAIMS_USER_PROMPT
