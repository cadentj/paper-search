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

DOCUMENT_SUMMARY_USER_PROMPT = """SQLADocument title: {filename}

Extracted text:

{document_text}

Write a concise summary for generating future research search filters."""

CLAIM_FILTER_SEARCH_SYSTEM_PROMPT = """You are a research item evaluator. Given a claim filter and a research item, determine whether the item supports or refutes the claim.

For each item, return:
- itemId, sourceType, sourceId: exact values from the input
- verdict: "positive" if the item supports, strengthens, or provides evidence for the claim; "negative" if the item refutes, weakens, challenges, or provides evidence against the claim.
- reason: 1-2 sentences explaining the relationship.
- evidence: (optional) a brief excerpt or specific finding from the item.

Only include items that genuinely relate to the claim. Ambiguous or mixed items should choose the stronger direction. Omit items that do not relate."""

TOPIC_FILTER_SEARCH_SYSTEM_PROMPT = """You are a research item evaluator. Given a topic filter and a research item, determine whether the item is relevant to the topic.

For each item, return:
- itemId, sourceType, sourceId: exact values from the input
- reason: 1-2 sentences explaining how the item relates to the topic.
- evidence: (optional) a brief excerpt or specific finding from the item.

Only include items that genuinely relate to the topic. Be selective."""

CLAIM_FILTER_SEARCH_USER_PROMPT = """Claim SQLAFilter:
Name: {filter_name}
Claim: {filter_description}

Item to evaluate:
{papers_text}

Determine whether this item supports or refutes the claim. Return an empty matches array if it does not relate."""

TOPIC_FILTER_SEARCH_USER_PROMPT = """Topic SQLAFilter:
Name: {filter_name}
Topic: {filter_description}

Item to evaluate:
{papers_text}

Determine whether this item is relevant to the topic. Return an empty matches array if it does not relate."""

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

FEEDBACK_REFLECTION_SYSTEM_PROMPT = """You are a research filter advisor. A researcher has provided feedback on paper matches and left notes on papers. Based on all of their feedback, propose changes to their filter set.

For each proposed change, choose one action:
- CREATE: propose a new filter for an uncovered research interest
- REVISE: update an existing filter's description to better match or exclude papers
- DELETE: remove a filter that is no longer useful

For REVISE and DELETE, you must specify the target_filter_id of the existing filter.
For CREATE and REVISE, provide a name, description, and mode ("claim" or "topic").

Consider the full picture of feedback before proposing changes. A single vote may not warrant a change, but patterns across multiple votes should inform your decisions."""

FEEDBACK_REFLECTION_USER_PROMPT = """Existing Filters:
{existing_filters}

Vote Feedback:
{vote_feedback}

Note Feedback:
{note_feedback}

Based on all feedback above, propose filter changes."""

SCHOLAR_PROFILE_SYSTEM_PROMPT = """You are an expert research assistant. Given a researcher's publication history from Semantic Scholar, generate targeted search filters that would help them keep up with relevant new papers.

Each filter should be one of two types:
- Topic filter (mode: "topic"): Search for papers relevant to a research topic or question.
- Claim filter (mode: "claim"): Search for evidence supporting, refuting, or complicating a specific proposition.

Generate 3-5 topic filters and 2-4 claim filters based on the researcher's publications and research interests. Focus on their most active and recent research areas."""

SCHOLAR_PROFILE_USER_PROMPT = """Researcher: {author_name}

Research Interests/Fields: {fields_of_study}

Recent and Notable Publications:
{publications_text}

Generate proposed search filters based on this researcher's publication history."""
