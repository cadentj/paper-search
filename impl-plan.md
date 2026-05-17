# Implementation Plan

## Summary

Build a prototype for a single researcher to keep up with relevant research by onboarding into natural-language filters and running those filters over daily paper batches.

The product center is not a generic paper feed. It is a daily view of what changed in the user's research interest space:

- Claims the user believes or wants tracked can be supported, refuted, or complicated by new papers.
- Questions the user cares about can be informed by relevant papers.
- Topics the user follows can surface broadly relevant work.

V1 should prioritize a coherent end-to-end experience with text-based onboarding, mocked arXiv abstracts, a real async backend shape, and a frontend layout that can later plug into real ingestion.

## Tech Stack

### Frontend

- Next.js App Router
- TypeScript
- Tailwind CSS
- shadcn/ui
- React Query via `@tanstack/react-query` for server state
- Zustand only for local UI state
- lucide-react for icons

Do not use TanStack Router for v1. The earlier plan mentioned both Next.js and TanStack Router, but the final decision is Next.js App Router.

### Backend

- FastAPI
- Python with `uv`
- SQLite
- Redis
- RQ for background jobs
- SQLAlchemy
- Alembic
- Pydantic
- OpenAI Python SDK for LLM jobs

### Local Development

Use Docker Compose for backend infrastructure:

- `api`: FastAPI server
- `worker`: RQ worker
- `redis`: queue and short-lived job state

SQLite is the durable app database. Store the local database in a mounted backend data directory, for example `backend/data/paper_search.db`, so the API and worker can both access the same file.

The frontend can run outside Docker with `pnpm dev` and talk to FastAPI through `NEXT_PUBLIC_API_URL`.

## Repository Shape

Recommended structure:

```txt
.
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── db/
│   │   ├── jobs/
│   │   ├── llm/
│   │   ├── models/
│   │   ├── schemas/
│   │   └── services/
│   ├── alembic/
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── app/
│   ├── components/
│   ├── lib/
│   ├── hooks/
│   └── stores/
├── docker-compose.yml
├── .env.example
├── plan.md
└── impl-plan.md
```

## Core Product Concepts

### Onboarding

Onboarding converts the user's research interests into initial filters.

V1 onboarding is text-only:

1. The user describes their current research interests, active hypotheses, open questions, and topics they want to track.
2. The backend extracts proposed claim/question/topic filters from that text.
3. The user reviews, edits, removes, or adds proposed filters.
4. The user confirms onboarding, which creates the selected filters.

Do not implement voice transcription, document upload, Google Docs import, paper import, or codebase ingestion in v1.

### Filter

A filter is a standing research interest. It is not just a saved keyword search. It contains the user-facing research statement plus instructions for how the LLM should judge papers against that statement.

Filter types:

- `claim`: a proposition the user believes or wants tracked.
- `question`: an open research question the user wants papers to inform.
- `topic`: a broader area the user wants to stay current on.
- `custom`: a user-defined filter type with custom judge instructions.

Examples:

- Claim: "LLM-as-judge evaluation is unreliable."
- Question: "When do SAE features become causally meaningful?"
- Topic: "Mechanistic interpretability for reasoning models."

Because onboarding is now in scope, do not silently seed filters into a fresh database. A fresh user should start on the onboarding flow. For demo resilience, the onboarding extraction endpoint can return deterministic fallback proposals if `OPENAI_API_KEY` is missing.

### Search Run

A search run is one execution of active filters over a paper batch.

For v1, the paper batch comes from a mocked arXiv endpoint that returns 10 deterministic abstract-like papers. Later, this can be replaced by real arXiv ingestion without changing the UI contract.

### Paper Match

A paper match is the LLM's judgment that a paper is relevant to a filter.

For claim filters, the important stance values are:

- `supports`
- `refutes`
- `complicates`
- `irrelevant`

For question and topic filters, the important stance values are:

- `relevant`
- `irrelevant`

### Idea Map

An idea map is generated lazily for a paper when the user opens it. It decomposes the paper into core claims, warrants, and evidence. In v1, the evidence can be based on mocked metadata or abstract-level text rather than real PDF extraction.

## Backend Data Models

The schema examples below describe the logical tables. Implement them with SQLAlchemy types that work on SQLite:

- IDs should be UUID strings stored as `TEXT`.
- Timestamps should use SQLAlchemy `DateTime`, stored by SQLite as text/datetime-compatible values.
- JSON fields should use SQLAlchemy `JSON`, stored by SQLite as JSON text.
- Scores can be `Float` in v1 instead of database-specific numeric types.

### `filters`

Stores standing user interests and the instructions used to judge papers.

```sql
filters (
  id text primary key,
  type text not null,
  name text not null,
  statement text not null,
  description text,

  judge_instructions text not null,
  rerank_instructions text,
  version integer not null default 1,

  active boolean not null default true,
  created_at datetime not null,
  updated_at datetime not null
)
```

Behavior:

- `statement` is the concise natural-language filter.
- `judge_instructions` tells the model how to evaluate abstracts for this filter.
- `rerank_instructions` tells the model how to order matches within the filter.
- `version` increments when judge or rerank instructions change.
- V1 does not need a separate table for filter type definitions.

### `onboarding_extractions`

Stores one onboarding extraction run from raw user text into proposed filters.

```sql
onboarding_extractions (
  id text primary key,
  status text not null,

  input_text text not null,
  proposed_filters json not null default '[]',
  error text,

  llm_model text,
  llm_response_id text,

  created_at datetime not null,
  updated_at datetime not null,
  completed_at datetime
)
```

Allowed `status` values:

- `queued`
- `running`
- `completed`
- `failed`

Suggested JSON shape for `proposed_filters`:

```ts
type ProposedFilter = {
  id: string
  type: "claim" | "question" | "topic"
  name: string
  statement: string
  description?: string
  rationale: string
  judgeInstructions: string
  rerankInstructions?: string
}
```

Behavior:

- Proposed filters are not active filters until the user confirms them.
- The frontend may edit proposed filters before saving them.
- If `OPENAI_API_KEY` is missing, return deterministic fallback proposals so the onboarding UI remains demoable.

### `papers`

Stores normalized paper records from the mocked arXiv source.

```sql
papers (
  id text primary key,
  external_id text unique,
  source text not null default 'mock_arxiv',

  title text not null,
  abstract text not null,
  authors json not null,
  categories json,
  published_at datetime,
  pdf_url text,
  landing_url text,

  created_at datetime not null,
  updated_at datetime not null
)
```

Behavior:

- `external_id` should be stable across mock runs so matches can reference papers consistently.
- `authors` can be a JSON array of strings.
- `categories` can mimic arXiv categories but does not need to be exhaustive.

### `search_runs`

Stores one execution of filters over a paper batch.

```sql
search_runs (
  id text primary key,
  mode text not null,
  status text not null,

  paper_source text not null default 'mock_arxiv',
  paper_limit integer not null default 10,

  started_at datetime,
  completed_at datetime,
  error text,

  created_at datetime not null
)
```

Allowed `mode` values:

- `daily`
- `manual`

Allowed `status` values:

- `queued`
- `running`
- `completed`
- `failed`

### `search_run_filters`

Snapshots the filter configuration used for a run.

```sql
search_run_filters (
  id text primary key,
  search_run_id text not null references search_runs(id),
  filter_id text not null references filters(id),

  filter_version integer not null,
  statement_snapshot text not null,
  judge_instructions_snapshot text not null,
  rerank_instructions_snapshot text
)
```

Reason:

Filters can evolve. A previous search run should still explain which filter text and instructions were used at the time it ran.

### `paper_matches`

Stores LLM judgments for filter-paper pairs.

```sql
paper_matches (
  id text primary key,
  search_run_id text not null references search_runs(id),
  filter_id text not null references filters(id),
  paper_id text not null references papers(id),

  stance text not null,
  relevance_score real not null,
  confidence real,

  rationale text not null,
  matched_claims json not null default '[]',
  abstract_evidence json not null default '[]',

  rank integer,
  llm_model text,
  llm_response_id text,

  created_at datetime not null
)
```

Behavior:

- Store irrelevant matches only if useful for debugging. The API should usually return relevant, supports, refutes, and complicates matches.
- `matched_claims` should be short claims extracted from the abstract.
- `abstract_evidence` should be snippets or sentence references from the abstract.
- `rank` is per filter within a search run.

### `idea_maps`

Stores generated paper decompositions.

```sql
idea_maps (
  id text primary key,
  paper_id text not null references papers(id),
  status text not null,

  claims json not null default '[]',
  llm_model text,
  llm_response_id text,
  error text,

  created_at datetime not null,
  updated_at datetime not null
)
```

Allowed `status` values:

- `queued`
- `running`
- `completed`
- `failed`

Suggested JSON shape for `claims`:

```ts
type IdeaMapClaim = {
  id: string
  claim: string
  importance: "central" | "supporting" | "minor"
  warrants: {
    id: string
    warrant: string
    evidence: {
      id: string
      kind: "abstract" | "paper_text" | "figure" | "citation"
      text: string
      page?: number
    }[]
  }[]
}
```

### `feedback`

Stores user feedback on matches and idea-map evidence.

```sql
feedback (
  id text primary key,
  target_type text not null,
  target_id text not null,

  value text not null,
  note text,

  created_at datetime not null
)
```

Allowed `target_type` values:

- `paper_match`
- `idea_map_claim`
- `evidence`

Allowed `value` values:

- `upvote`
- `downvote`
- `not_interested`

V1 stores feedback but does not need to rewrite prompts from feedback yet.

## LLM Output Contracts

Use structured outputs with Pydantic schemas in the worker. The worker should normalize model output before writing to SQLite through the same SQLAlchemy models used by the API.

### Onboarding Extraction Output

```ts
type OnboardingExtractionOutput = {
  proposedFilters: {
    type: "claim" | "question" | "topic"
    name: string
    statement: string
    description?: string
    rationale: string
    judgeInstructions: string
    rerankInstructions?: string
  }[]
}
```

The extraction prompt should prefer a small, high-quality set of filters over a long list. Target 2-4 claims, 2-3 questions, and 1-3 topics unless the user's input clearly calls for fewer.

### Filter Judge Output

```ts
type FilterJudgeOutput = {
  matches: {
    paperExternalId: string
    stance: "supports" | "refutes" | "complicates" | "relevant" | "irrelevant"
    relevanceScore: number
    confidence: number
    rationale: string
    matchedClaims: string[]
    abstractEvidence: string[]
  }[]
}
```

### Rerank Output

```ts
type RerankOutput = {
  rankings: {
    paperExternalId: string
    rank: number
    reason: string
  }[]
}
```

### Idea Map Output

```ts
type IdeaMapOutput = {
  claims: IdeaMapClaim[]
}
```

## Backend API

### Health

```http
GET /health
```

Returns service health and basic dependency status.

### Mock arXiv

```http
GET /mock/arxiv?limit=10
```

Returns 10 deterministic mock paper abstracts.

This endpoint exists to keep frontend and backend development unblocked before real arXiv ingestion.

### Onboarding

```http
GET /onboarding/status
POST /onboarding/extractions
GET /onboarding/extractions/{extraction_id}
POST /onboarding/complete
```

`GET /onboarding/status` behavior:

- Return whether onboarding is complete.
- For v1, onboarding is complete when at least one active filter exists.
- Include active filter count.

`POST /onboarding/extractions` behavior:

1. Accept a raw text description of the user's interests.
2. Create an `onboarding_extractions` row with `queued` status.
3. Enqueue an RQ job to extract proposed filters.
4. Return the extraction id.

`GET /onboarding/extractions/{id}` returns extraction status, proposed filters, and any error.

`POST /onboarding/complete` behavior:

1. Accept the user's edited list of proposed filters.
2. Create active `filters` rows using default instructions where needed.
3. Return created filters.

### Filters

```http
GET /filters
POST /filters
PATCH /filters/{filter_id}
DELETE /filters/{filter_id}
```

Delete can soft-disable by setting `active = false`.

For built-in filter types, `POST /filters` should fill in default judge and rerank instructions if the request does not provide custom instructions.

### Search Runs

```http
GET /search-runs/latest
POST /search-runs
GET /search-runs/{search_run_id}
GET /search-runs/{search_run_id}/matches
```

`POST /search-runs` behavior:

1. Create `search_runs` row with `queued` status.
2. Snapshot all active filters into `search_run_filters`.
3. Load 10 mock arXiv papers and upsert them into `papers`.
4. Enqueue one RQ job for the run.

`GET /search-runs/{id}/matches` should return results grouped by filter for the Daily page.

### Papers and Idea Maps

```http
GET /papers/{paper_id}
POST /papers/{paper_id}/idea-map
GET /papers/{paper_id}/idea-map
```

`POST /papers/{paper_id}/idea-map` behavior:

1. Return existing completed idea map if present.
2. Return existing queued or running idea map if already in progress.
3. Otherwise create an `idea_maps` row and enqueue an RQ job.

### Feedback

```http
POST /feedback
```

Records user feedback on paper matches, claims, or evidence.

## Worker Jobs

### `extract_onboarding_filters(extraction_id)`

Flow:

1. Mark extraction `running`.
2. Load the raw onboarding text.
3. If `OPENAI_API_KEY` is configured, ask the model for proposed claim/question/topic filters using the structured output schema.
4. If `OPENAI_API_KEY` is missing, use deterministic fallback proposals from the same schema shape.
5. Persist normalized `proposed_filters`.
6. Mark extraction `completed`.
7. On failure, mark `failed` and store the error.

### `run_search(search_run_id)`

Main job for a search run.

Flow:

1. Mark run `running`.
2. Load run filter snapshots.
3. Load the paper batch.
4. For each filter snapshot, call the LLM judge over all 10 abstracts.
5. Persist `paper_matches`.
6. Run reranking for each filter if multiple relevant matches exist.
7. Mark run `completed`.
8. If any unrecoverable error occurs, mark run `failed` and store the error.

The v1 paper batch is small enough that one job can process all filters. Later this can split into one job per filter or per paper batch.

### `generate_idea_map(idea_map_id)`

Flow:

1. Mark idea map `running`.
2. Load paper metadata and abstract.
3. Ask the model for core claims, warrants, and evidence.
4. Persist normalized `claims` JSON.
5. Mark idea map `completed`.
6. On failure, mark `failed` and store the error.

## Frontend Data Fetching

Use React Query for backend state. Do not store backend entities in Zustand.

Recommended API client:

```ts
api.getOnboardingStatus()
api.createOnboardingExtraction(input)
api.getOnboardingExtraction(id)
api.completeOnboarding(input)
api.getFilters()
api.createFilter(input)
api.updateFilter(id, input)
api.deleteFilter(id)
api.getLatestSearchRun()
api.createSearchRun(input)
api.getSearchRun(id)
api.getSearchRunMatches(id)
api.getPaper(id)
api.getPaperIdeaMap(paperId)
api.generatePaperIdeaMap(paperId)
api.submitFeedback(input)
```

Recommended query keys:

```ts
["onboarding", "status"]
["onboarding", "extractions", extractionId]
["filters"]
["search-runs", "latest"]
["search-runs", runId]
["search-runs", runId, "matches"]
["papers", paperId]
["papers", paperId, "idea-map"]
```

Polling behavior:

- Poll onboarding extraction status while status is `queued` or `running`.
- Poll search run status while status is `queued` or `running`.
- Poll idea map status while status is `queued` or `running`.
- Use React Query `refetchInterval` for polling, with a default interval around 1000ms while jobs are active.
- Keep previous Daily results visible while a new run is in progress.
- Do not implement WebSockets or Server-Sent Events in v1.

Use Zustand only for UI state:

```ts
type UiState = {
  selectedFilterType: "all" | "claim" | "question" | "topic" | "custom"
  selectedRunId?: string
  selectedPaperId?: string
  selectedIdeaClaimId?: string
  selectedEvidenceId?: string
}
```

## Frontend Pages and Layout

### App Shell

Use a shadcn sidebar layout after onboarding with three primary routes:

- `Daily`
- `Filters`
- `Search`

`Search` exists in the sidebar but is not fully implemented in v1.

Before onboarding is complete, route the user to `/onboarding` rather than the sidebar app shell.

### Onboarding Page

Route:

```txt
/onboarding
```

Layout:

- Full-page focused form, not inside the sidebar shell.
- Large text area asking the user to describe current research interests, hypotheses, questions, and topics.
- Submit action starts an onboarding extraction.
- While extraction is queued/running, show progress using React Query polling.
- Once extraction completes, show editable proposed filters grouped by `claim`, `question`, and `topic`.
- The user can edit text, remove weak proposals, add a manual filter, and complete onboarding.
- Completing onboarding creates filters and routes to `Daily`.

### Daily Page

This is the default first screen.

Content:

- Header with today's search status.
- Primary action: run daily search.
- Grouped sections by filter.
- Within each filter, paper cards sorted by rank or relevance.
- Each paper card shows title, authors, date, stance badge, relevance score, rationale, matched claims, and abstract evidence.

Card interactions:

- Open paper detail page.
- Submit feedback.
- Show enough rationale that the user understands why the paper appeared.

### Filters Page

Content:

- List all active filters.
- Show filter type, statement, description, and version.
- Show judge/rerank instruction previews in an expandable area.
- Support creating a new filter.
- Support disabling a filter.

Creating a filter:

- Choose type.
- Enter name.
- Enter statement.
- Optionally enter description.
- For built-in types, backend can provide default judge instructions.
- For custom type, user can provide judge instructions.

### Paper Detail Page

Route:

```txt
/papers/[paperId]
```

Layout:

- Left pane: idea map.
- Right pane: PDF-style viewer placeholder.

V1 paper viewer behavior:

- Show paper title and metadata.
- Show PDF URL if available.
- Use a stable placeholder panel for the PDF if embedding is not worth the time.
- Clicking an idea-map claim or warrant updates selected evidence/page state.

### Search Page

V1 placeholder.

Content:

- Disabled controls for selecting filters.
- Disabled date range control.
- Short note that manual historical search is out of scope for v1.

Do not implement actual historical search in v1.

## Implementation Order

### Phase 1: Scaffold

1. Create frontend Next.js app.
2. Add shadcn/ui and sidebar components.
3. Create backend FastAPI app.
4. Add Docker Compose for Redis, API, and worker.
5. Add `.env.example`.

### Phase 2: Backend Foundation

1. Define SQLAlchemy models.
2. Add Alembic migrations.
3. Add database session handling.
4. Add onboarding status, extraction, and completion endpoints.
5. Add filter CRUD endpoints.
6. Add deterministic mock arXiv service.
7. Add search run creation and status endpoints.

### Phase 3: Queue and LLM Jobs

1. Add Redis/RQ connection setup.
2. Add worker entrypoint.
3. Implement `extract_onboarding_filters`.
4. Implement `run_search`.
5. Implement OpenAI structured judge call.
6. Persist matches and run status.
7. Implement `generate_idea_map`.

### Phase 4: Frontend Data Layer

1. Add React Query provider.
2. Add API client.
3. Add query and mutation hooks.
4. Connect Onboarding page to extraction and completion endpoints.
5. Connect Filters page to backend.
6. Connect Daily page to search runs and matches.
7. Connect Paper page to idea-map endpoints.

### Phase 5: Product Polish

1. Make Daily page dense and readable.
2. Add stance badges and rationale presentation.
3. Add loading, empty, queued, running, completed, and failed states.
4. Add feedback controls.
5. Polish onboarding proposal review and edit states.
6. Add Search placeholder route.
7. Add README instructions for running the prototype.

## Out of Scope for V1

- Automated tests. User will handle testing separately.
- Real arXiv ingestion.
- PDF parsing.
- Voice transcription, document upload, Google Docs import, paper import, and codebase ingestion during onboarding.
- Embeddings or vector search.
- Auth.
- Multi-user support.
- Scheduled daily jobs.
- Prompt self-rewriting from feedback.
- Citation graph visualization.
- Historical search over prior months.

## Environment Variables

```txt
DATABASE_URL=sqlite:///./data/paper_search.db
REDIS_URL=redis://redis:6379/0
OPENAI_API_KEY=
OPENAI_MODEL=
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Use a sensible backend default model if `OPENAI_MODEL` is empty, but require `OPENAI_API_KEY` for real LLM jobs.

When running API and worker in Docker, use a shared mounted volume and an absolute SQLite URL such as:

```txt
DATABASE_URL=sqlite:////app/data/paper_search.db
```

Enable SQLite WAL mode during database initialization so the API and worker can safely share reads and writes for this single-user prototype.

## Acceptance Criteria

- The repo has a runnable frontend and backend.
- Docker Compose starts Redis, FastAPI, and the RQ worker.
- A fresh user starts on the onboarding page.
- The user can enter research interests and generate proposed filters.
- The user can edit proposed filters and complete onboarding.
- After onboarding, the frontend opens to the Daily dashboard.
- The user can create and view filters.
- The user can start a search run from the Daily page.
- The backend enqueues a Redis job for the search run.
- The worker evaluates mocked abstracts with the active filters and stores matches.
- The Daily page displays grouped matches with stance, score, rationale, and evidence.
- The user can open a paper detail page.
- The user can generate and view an idea map for that paper.
- The Search page exists as a v1 placeholder but does not implement historical search.
