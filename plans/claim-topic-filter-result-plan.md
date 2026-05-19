# Claim/Topic Filter Result Plan

## Summary

Update daily search so each filter mode has its own structured LLM output and
mode-specific rendering. Drop the older custom-filter/question direction and
make `claim` and `topic` the only supported filter modes.

For this prototype, no migration or backward compatibility work is needed. The
database can be dropped during development churn, so the current text
`paper_matches.result` field can be replaced with structured JSON.

## Key Changes

- Keep `FilterDefinition.mode` as only `"claim" | "topic"`.
- Replace `paper_matches.result: text` with `paper_matches.result: JSON/JSONB`.
- Add mode-specific LLM response schemas:
  - Claim result:
    ```ts
    {
      verdict: "positive" | "negative"
      reason: string
      evidence?: string
    }
    ```
  - Topic result:
    ```ts
    {
      reason: string
      evidence?: string
    }
    ```
- For claim filters:
  - `positive` means the paper supports, strengthens, or provides evidence for
    the user's claim.
  - `negative` means the paper refutes, weakens, challenges, or provides
    evidence against the claim.
  - Ambiguous or mixed papers must choose the stronger direction for v1.
  - Non-matches are omitted, not stored with a neutral verdict.
- For topic filters:
  - Store only relevant matches with a concise reason and optional excerpt or
    evidence.

## Backend Implementation

- Split the current `FilterSearchResponse` into mode-specific Pydantic response
  models, for example `ClaimFilterSearchResponse` and
  `TopicFilterSearchResponse`.
- In `run_daily_search`, choose the response model and prompt wording from
  `filter.definition.mode`.
- Persist the parsed result object directly into `PaperMatch.result`.
- Update `PaperMatchResponse.result` to be a `dict` instead of a `str`.
- Update summary generation to format structured results into readable text
  before sending matches to the summary LLM.
- Since the database will be dropped during dev churn, do not add Alembic
  migrations or compatibility shims for the old text result column.

## Frontend Implementation

- Update the `PaperMatch.result` TypeScript type from `string` to a union:
  ```ts
  type ClaimMatchResult = {
    verdict: "positive" | "negative"
    reason: string
    evidence?: string
  }

  type TopicMatchResult = {
    reason: string
    evidence?: string
  }
  ```
- Include filter mode in match data, either by exposing `filter_mode` on
  `PaperMatchResponse` or by deriving it from the filter definition where
  available.
- Daily page rendering:
  - Continue grouping matches by filter.
  - For claim filters, split each group into `Positive` and `Negative` buckets.
  - For topic filters, render the current flat list style using `reason`.
  - Show a small verdict badge on claim match cards.
- Search history should use the same match renderer as Daily so historical runs
  display consistently.

## Test Plan

- Backend:
  - Unit test that claim filters use the claim response schema and persist JSON
    verdicts.
  - Unit test that topic filters use the topic response schema and persist JSON
    reasons.
  - Worker test that empty/non-match outputs do not create `PaperMatch` rows.
  - Summary test that structured match JSON is converted into readable summary
    input.
- Frontend:
  - Daily page test showing claim matches bucketed into Positive and Negative
    sections.
  - Daily page test showing topic matches render as normal relevance cards.
  - Search history test that structured result JSON renders without raw JSON
    leaking into UI.

## Assumptions

- Database reset is acceptable; no backward compatibility or migration path is
  needed.
- V1 claim verdicts are exactly `positive` and `negative`.
- Mixed evidence is forced into the dominant verdict for simplicity.
- Questions remain folded into topic filters rather than returning as a separate
  mode.
