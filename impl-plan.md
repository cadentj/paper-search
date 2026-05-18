# Implementation Plan

## Summary

Build a local single-user prototype that helps a researcher keep up with relevant papers by:

1. Onboarding them into natural-language filters.
2. Running daily searches over a small paper batch.
3. Showing a cited Daily summary and grouped paper matches.
4. Letting the user archive filters or hide uninteresting matches.
5. Generating HTML-based idea maps for opened papers.

V1 should feel like a coherent research workflow, not a generic paper database. Production deployment, multi-user support, custom historical searches, and non-HTML paper parsing are out of scope.

## Stack

### Frontend

- Next.js App Router
- TypeScript
- Tailwind CSS
- shadcn/ui
- `@tanstack/react-query` for server state and polling
- Zustand only for local UI state
- lucide-react for icons

### Backend

- FastAPI
- Python with `uv`
- SQLite
- Redis
- RQ background jobs
- SQLAlchemy
- Alembic
- Pydantic
- OpenRouter LLM calls using `deepseek/deepseek-v4-flash` with provider `novita`

### Local Runtime

Use Docker Compose for:

- `api`: FastAPI server
- `worker`: RQ worker
- `redis`: queue

SQLite lives in a mounted backend data directory, for example `backend/data/paper_search.db`, shared by API and worker. Enable SQLite WAL mode during initialization.

The frontend runs with `pnpm dev` and calls FastAPI through `NEXT_PUBLIC_API_URL`.

## Repository Shape

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
│   ├── hooks/
│   ├── lib/
│   └── stores/
├── docker-compose.yml
├── .env.example
├── plan.md
└── impl-plan.md
```

## Product Model

### Onboarding

Onboarding is text-only.

The user enters freeform notes about:

- current research interests
- hypotheses they are tracking
- open questions
- broad topics they want to follow

The backend converts this into proposed filters using three default templates:

- Claim template: search for warrants for or against a proposition.
- Question template: search for answers or partial answers to a question.
- Topic template: search for abstracts relevant to a topic.

The user can edit, remove, or add proposed filters before completing onboarding.

Onboarding is complete when at least one filter has `status = "active"`.

### Filters

A filter is a JSON-defined search instruction. There is no top-level `kind` enum and no versioning.

```ts
type FilterDefinition = {
  name: string
  statement: string
  description?: string
  search: {
    instructions: string
    outputMode: "warrants" | "answers" | "relevance"
  }
}
```

Filters have lifecycle state:

```ts
type FilterStatus = "active" | "archived"
```

- `active`: included in daily searches.
- `archived`: shown in an archived section on the Filters page, not run.

Clicking Not Interested on a filter archives it. The filter is not deleted.

### Daily Searches

V1 has only daily searches. There is no custom search mode.

A daily search run:

1. Loads current active filters.
2. Loads the daily paper batch from an internal deterministic mock paper provider.
3. Runs each active filter over the paper abstracts.
4. Stores paper matches.
5. Generates a concise cited summary over surfaced matches.

The mock paper provider is an implementation detail, not a persisted paper source in the data model.

### Search History

The Search page is a history page for previous daily searches.

It should list prior daily search runs and let the user open a run to inspect:

- status
- generated summary
- summary citations
- grouped paper matches

The Search page does not start custom searches in v1.

### Persistence Policy

Keep local data persistently unless the user uses the dev reset control.

- Filters persist as active or archived.
- Papers persist.
- Cached arXiv HTML persists.
- Daily search runs persist as history.
- Paper matches persist as historical results.
- Idea maps persist and are reused.

Paper matches are historical results and are not hidden by per-match controls in v1.

### Idea Maps

An idea map is generated from arXiv HTML when the user opens a paper.

It is intentionally simple:

- A paper has claims.
- Each claim has warrants.
- Each warrant has one citation into the HTML text.
- If a warrant needs multiple citations, split it into multiple warrants under the same claim.

Click behavior:

- Click claim: expand or collapse warrants.
- Click warrant: jump the HTML viewer to the cited text and highlight it.

Papers without arXiv HTML are skipped for idea-map generation.

## Data Models

Use SQLAlchemy types compatible with SQLite:

- IDs are UUID strings stored as `TEXT`.
- Timestamps use SQLAlchemy `DateTime`.
- JSON fields use SQLAlchemy `JSON`.
- Scores use `Float`.

### `filters`

```sql
filters (
  id text primary key,
  name text not null,
  definition json not null,
  status text not null default 'active',

  created_at datetime not null,
  updated_at datetime not null,
  archived_at datetime
)
```

Notes:

- `name` is denormalized from `definition.name`.
- `definition` is the source of truth for statement and search instructions.
- Filters are not versioned.
- Archived filters are not run.

### `onboarding_extractions`

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

Allowed statuses:

- `queued`
- `running`
- `completed`
- `failed`

Proposed filter shape:

```ts
type ProposedFilter = {
  id: string
  name: string
  rationale: string
  definition: FilterDefinition
}
```

### `papers`

```sql
papers (
  id text primary key,
  arxiv_id text unique,

  title text not null,
  abstract text not null,
  authors json not null,
  categories json,
  published_at datetime,
  html_url text,
  landing_url text,

  created_at datetime not null,
  updated_at datetime not null
)
```

Notes:

- `arxiv_id` is stable and used to construct `https://arxiv.org/html/{arxiv_id}`.
- V1 daily paper records come from the internal mock provider, but are stored as normal papers.

### `paper_html`

Cache fetched arXiv HTML.

```sql
paper_html (
  paper_id text primary key references papers(id),
  source_url text not null,
  html text not null,
  content_hash text,
  fetched_at datetime not null
)
```

### `search_runs`

One row per daily search execution.

```sql
search_runs (
  id text primary key,
  status text not null,
  run_date date not null,

  candidate_count integer,
  match_count integer,
  summary text,
  summary_citations json not null default '[]',
  stage text not null default 'queued',
  progress_current integer not null default 0,
  progress_total integer not null default 1,
  progress_message text not null default 'Queued',
  progress_log json not null default '[]',

  started_at datetime,
  completed_at datetime,
  error text,
  created_at datetime not null
)
```

Allowed statuses:

- `queued`
- `running`
- `completed`
- `failed`

`run_date` is not unique. Local demos may create multiple daily runs on the same date.

### `paper_matches`

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

  llm_model text,
  llm_response_id text,
  created_at datetime not null
)
```

Expected stance values:

- `supports`
- `refutes`
- `complicates`
- `relevant`
- `irrelevant`

The API should hide irrelevant matches by default.

### `idea_maps`

```sql
idea_maps (
  id text primary key,
  paper_id text not null references papers(id),
  status text not null,

  claims json not null default '[]',
  source_url text,
  dropped_reason text,
  llm_model text,
  llm_response_id text,
  error text,

  created_at datetime not null,
  updated_at datetime not null
)
```

Allowed statuses:

- `queued`
- `running`
- `completed`
- `failed`
- `skipped`

Idea map JSON:

```ts
type IdeaMap = {
  claims: IdeaMapClaim[]
}

type IdeaMapClaim = {
  id: string
  text: string
  warrants: IdeaMapWarrant[]
}

type IdeaMapWarrant = {
  id: string
  text: string
  citation: HtmlCitation
}

type HtmlCitation = {
  blockId: string
  quote: string
  prefix?: string
  suffix?: string
  htmlAnchor: string
  sectionTitle?: string
}
```

Citation validation:

- Parse arXiv HTML into addressable blocks.
- Model must cite a `blockId` and exact quote or prefix/suffix.
- Verify the block exists.
- Verify the quote exists in the block text, or prefix/suffix identify a valid span.
- Drop invalid warrants or run one repair pass.
- Store only validated citations.

## LLM Contracts

Use structured outputs with Pydantic schemas in worker code. The LLM client should call OpenRouter with:

- `OPENROUTER_API_KEY`
- model `deepseek/deepseek-v4-flash`
- provider `novita`

### Onboarding Extraction

```ts
type OnboardingExtractionOutput = {
  proposedFilters: ProposedFilter[]
}
```

Prompt target:

- 2-4 warrant-search filters
- 2-3 answer-search filters
- 1-3 relevance-search filters

Prefer fewer high-quality filters over a long list.

### Filter Search

```ts
type FilterSearchOutput = {
  matches: {
    arxivId: string
    stance: "supports" | "refutes" | "complicates" | "relevant" | "irrelevant"
    relevanceScore: number
    confidence: number
    rationale: string
    matchedClaims: string[]
    abstractEvidence: string[]
  }[]
}
```

### Daily Summary

```ts
type SearchRunSummaryOutput = {
  summary: string
  citations: {
    paperMatchId?: string
    arxivId: string
    citedFor: string
  }[]
}
```

### Idea Map

```ts
type IdeaMapOutput = IdeaMap
```

Definitions for the idea-map prompt:

- Claim: a concise proposition the paper argues, demonstrates, or relies on.
- Warrant: the specific reason the paper gives for believing the claim. This is usually a result, experiment, theorem, ablation, argument, or comparison.
- Citation: the exact HTML text location that justifies the warrant.

The model should split warrants if one warrant needs multiple citations.

## Backend API

### Health

```http
GET /health
```

### Onboarding

```http
GET /onboarding/status
POST /onboarding/extractions
GET /onboarding/extractions/{extraction_id}
POST /onboarding/complete
POST /dev/reset-onboarding
```

`GET /onboarding/status` returns whether at least one active filter exists.

`POST /onboarding/extractions` creates an extraction row and enqueues `extract_onboarding_filters`.

`POST /onboarding/complete` accepts edited proposed filters, creates active filters, and returns them.

`POST /dev/reset-onboarding` is local-development only. Enable it only when `APP_ENV=development` or `ENABLE_DEV_RESET=true`.

Reset behavior:

1. Delete onboarding extractions.
2. Delete idea maps.
3. Delete paper matches.
4. Delete search run paper associations.
5. Delete search runs.
6. Delete filters.
7. Keep papers and `paper_html` by default.

The endpoint returns counts for changed rows and fails outside development mode.

### Filters

```http
GET /filters
POST /filters
PATCH /filters/{filter_id}
POST /filters/{filter_id}/archive
POST /filters/{filter_id}/restore
```

`GET /filters` should support active and archived sections. Archived filters are visible but not run.

### Daily Search Runs

```http
GET /search-runs
GET /search-runs/latest
POST /search-runs/daily
GET /search-runs/{search_run_id}
GET /search-runs/{search_run_id}/matches
```

`POST /search-runs/daily` flow:

1. Create `search_runs` row with `queued` status and today's `run_date`.
2. Enqueue `run_daily_search` into Redis/RQ.
3. Return immediately with queued progress state.
4. If enqueue fails, mark the run failed and return HTTP 503.

`GET /search-runs` powers the Search history page.

### Papers and Idea Maps

```http
GET /papers/{paper_id}
POST /papers/{paper_id}/idea-map
GET /papers/{paper_id}/idea-map
```

`POST /papers/{paper_id}/idea-map` flow:

1. Return existing completed idea map if present.
2. Return existing queued/running/skipped idea map if present.
3. Otherwise create `idea_maps` row and enqueue `generate_idea_map`.

## Worker Jobs

### `extract_onboarding_filters(extraction_id)`

1. Mark extraction `running`.
2. Load raw onboarding text.
3. Ask the model for proposed filters using default templates and structured output.
4. Persist `proposed_filters`.
5. Mark extraction `completed`.
6. On failure, mark `failed` and store the error.

### `run_daily_search(search_run_id)`

1. Mark run `running`.
2. Fetch the latest arXiv batch, upsert papers, and persist the run's candidate papers.
3. Update persisted progress and logs after each major stage.
4. Load active filters.
5. For each active filter, search all abstracts using `filter.definition.search`.
6. Persist `paper_matches`.
7. Generate a concise Daily summary over visible surfaced matches.
8. Persist summary, citations, `candidate_count`, and `match_count`.
9. Mark run `completed`.
10. On failure, mark `failed`, store the error, and update progress.

### `generate_idea_map(idea_map_id)`

1. Mark idea map `running`.
2. Load paper metadata and construct `https://arxiv.org/html/{arxiv_id}`.
3. Fetch arXiv HTML, or load it from `paper_html` if cached.
4. If HTML is unavailable, mark idea map `skipped`, store `dropped_reason`, and log the drop.
5. Cache fetched HTML in `paper_html`.
6. Parse HTML into addressable blocks, preserving section titles.
7. Add local DOM anchors for useful blocks if needed.
8. Ask the model for claims and warrant citations from the block list.
9. Validate every warrant citation against parsed block text.
10. Persist validated claims/warrants.
11. Mark idea map `completed`.
12. On failure, mark `failed` and store the error.

## Frontend Data Fetching

Use React Query for backend state. Do not store backend entities in Zustand.

Recommended API client:

```ts
api.getOnboardingStatus()
api.createOnboardingExtraction(input)
api.getOnboardingExtraction(id)
api.completeOnboarding(input)
api.resetOnboardingDev()
api.getFilters(params)
api.createFilter(input)
api.updateFilter(id, input)
api.archiveFilter(id)
api.restoreFilter(id)
api.getSearchRuns()
api.getLatestSearchRun()
api.createDailySearchRun()
api.getSearchRun(id)
api.getSearchRunMatches(id)
api.getPaper(id)
api.getPaperIdeaMap(paperId)
api.generatePaperIdeaMap(paperId)
```

Recommended query keys:

```ts
["onboarding", "status"]
["onboarding", "extractions", extractionId]
["filters", status]
["search-runs"]
["search-runs", "latest"]
["search-runs", runId]
["search-runs", runId, "matches"]
["papers", paperId]
["papers", paperId, "idea-map"]
```

Polling:

- Poll onboarding extraction status while `queued` or `running`.
- Poll search run status while `queued` or `running`.
- Poll idea map status while `queued` or `running`.
- Use React Query `refetchInterval`, around 1000ms while jobs are active.
- Do not implement WebSockets or Server-Sent Events in v1.

Zustand should only hold local UI state:

```ts
type UiState = {
  selectedRunId?: string
  selectedPaperId?: string
  selectedIdeaClaimId?: string
  selectedIdeaWarrantId?: string
}
```

## Frontend Layout

### App Shell

After onboarding, use a shadcn sidebar layout with:

- `Daily`
- `Search`
- `Filters`

Before onboarding is complete, route to `/onboarding`.

### Onboarding Page

Route:

```txt
/onboarding
```

Layout:

- Full-page focused form outside the sidebar shell.
- In local development, include a small reset control.
- Large text area for research interests, hypotheses, questions, and topics.
- Submit starts extraction.
- Poll extraction status.
- Show editable proposed filters when complete.
- User can edit, remove, add, then complete onboarding.
- Completing onboarding routes to `Daily`.

### Daily Page

Default post-onboarding page.

Content:

- Header with latest daily search status.
- Primary action: run daily search.
- Lightweight add-filter box for quickly adding a claim, question, topic, or custom search instruction.
- Generated Daily summary with citations to surfaced papers.
- Grouped paper matches by filter.
- Paper cards with title, authors, date, stance, score, rationale, matched claims, and abstract evidence.

Interactions:

- Open paper detail.
- Not Interested on a filter group archives that filter.

### Search Page

Search is history-only in v1.

Content:

- List previous daily search runs.
- Show run date, status, match count, and summary preview.
- Opening a run shows summary and grouped matches.
- No controls for starting custom searches.
- No date-range search.
- No selected-filter search.

### Filters Page

Content:

- Active filters section.
- Archived filters section.
- Local-development reset action in a low-prominence menu or footer.
- Filter name, statement, description.
- Expand to inspect search instructions.
- Create, edit, archive, and restore filters.

Creating a filter:

- Start from Claim, Question, Topic, or Blank template.
- Enter name, statement, optional description.
- Edit search instructions if needed.

### Paper Detail Page

Route:

```txt
/papers/[paperId]
```

Layout:

- Left pane: idea map.
- Right pane: arXiv HTML viewer.

Behavior:

- If the idea map has not been generated, show a generate action.
- If generation is running, poll status.
- If skipped, show a concise unavailable state.
- Claims appear as collapsible rows.
- Clicking a claim expands or collapses warrants.
- Clicking a warrant jumps the right pane to the cited HTML anchor and highlights the cited text.
- Include a small add-filter control so an interesting paper claim can become a new filter.

## Tests

Tests should act as executable acceptance criteria for a cloud agent implementing the app.

### Backend Unit Tests

- Filter template normalization:
  - Claim template produces `outputMode = "warrants"`.
  - Question template produces `outputMode = "answers"`.
  - Topic template produces `outputMode = "relevance"`.
  - Persisted filters do not require a top-level `kind`.
  - Persisted filters are not versioned.
- Filter lifecycle:
  - Active filters are run.
  - Archived filters are not run.
  - Archived filters can be restored.
- arXiv provider:
  - Parses arXiv Atom records.
  - Records include stable arXiv ids, abstracts, authors, dates, and HTML URLs.
- HTML parser:
  - Parses sample arXiv-like HTML into addressable blocks.
  - Preserves section titles.
  - Generates stable anchors for blocks without usable anchors.
- Citation validation:
  - Accepts exact quote matches.
  - Accepts valid prefix/suffix matches.
  - Rejects missing block ids.
  - Rejects ambiguous or missing text spans.
- SQLite setup:
  - Initializes schema.
  - Enables WAL mode.

### Backend API Integration Tests

- Fresh database reports onboarding incomplete.
- Completing onboarding creates active filters.
- Dev reset clears onboarding/filter/search state and returns onboarding to incomplete.
- Dev reset is unavailable outside development mode.
- Filter CRUD supports create, update, archive, restore, and list.
- `POST /search-runs/daily` creates a queued daily run using current active filters.
- Archived filters are not used in daily runs.
- `GET /search-runs` returns daily search history.
- `POST /papers/{id}/idea-map` is idempotent for queued/running/completed/skipped maps.

### Worker Tests

- Run job functions directly against a temporary SQLite database.
- `extract_onboarding_filters` persists proposed filters.
- `run_daily_search` persists paper matches and a Daily summary.
- `run_daily_search` ignores archived filters.
- `generate_idea_map` uses cached HTML when present.
- `generate_idea_map` marks unavailable HTML as `skipped`.
- `generate_idea_map` persists only validated warrant citations.

### LLM Configuration Tests

- TOML model/provider config loads all required profiles.
- LLM client request bodies route each profile to its configured model/provider.
- Retry behavior remains covered with mocked OpenRouter responses.

Assert schema shape and minimal semantic behavior, not exact wording.

### Frontend Tests

- Onboarding form submits and shows running state.
- Completed extraction renders editable proposed filters.
- Completing onboarding routes to Daily.
- Daily shows loading, empty, running, completed, and failed states.
- Search page lists previous daily runs.
- Filters page shows active and archived filters.
- Not Interested archives a filter.
- Paper detail shows generate, running, skipped, and completed idea-map states.
- Clicking a claim expands warrants.
- Clicking a warrant calls HTML jump/highlight behavior.

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
3. Add SQLite WAL initialization.
4. Add database session handling.
5. Add onboarding endpoints.
6. Add filter CRUD/archive/restore endpoints.
7. Add real arXiv daily paper provider.
8. Add daily search run endpoints.
9. Add dev reset endpoint.

### Phase 3: Jobs and LLM

1. Add Redis/RQ connection setup.
2. Add worker entrypoint.
3. Implement `extract_onboarding_filters`.
4. Implement `run_daily_search`.
5. Implement Daily summary generation.
6. Implement HTML fetching/caching/parsing.
7. Implement `generate_idea_map`.

### Phase 4: Frontend Data Layer

1. Add React Query provider.
2. Add API client.
3. Add query and mutation hooks.
4. Connect onboarding.
5. Connect filters.
6. Connect Daily.
7. Connect Search history.
8. Connect paper detail and idea maps.

### Phase 5: Product Polish

1. Make Daily dense and readable.
2. Add loading, empty, running, skipped, completed, and failed states.
3. Polish cited summary display.
4. Polish Search history display.
5. Polish idea-map expansion and HTML jump behavior.
6. Add filter archive controls.
7. Add README instructions.

### Phase 6: Tests

1. Add backend unit tests.
2. Add backend API integration tests.
3. Add worker tests.
4. Add opt-in OpenRouter smoke tests.
5. Add frontend tests.
6. Document test commands in README.

## Out of Scope for V1

- Custom searches from the Search page.
- Date-range search.
- Search over selected filter subsets.
- Non-HTML paper parsing for idea maps.
- Embeddings or vector search.
- Auth.
- Multi-user support.
- Scheduled daily jobs.
- Citation graph visualization.

## Environment Variables

```txt
DATABASE_URL=sqlite:///./data/paper_search.db
REDIS_URL=redis://redis:6379/0
OPENROUTER_API_KEY=
NEXT_PUBLIC_API_URL=http://localhost:8000
```

When API and worker run in Docker, use:

```txt
DATABASE_URL=sqlite:////app/data/paper_search.db
```

## Acceptance Criteria

- The repo has a runnable frontend and backend.
- Docker Compose starts Redis, FastAPI, and the RQ worker.
- A fresh user starts on onboarding.
- The user can generate, edit, and save proposed filters.
- Active filters are run; archived filters are not run.
- In local development, the user can reset onboarding and rerun it.
- The user can run a daily search.
- Daily search produces grouped matches and a cited summary.
- Not Interested on a filter archives it.
- Not Interested on a paper match hides it from default results.
- Search page displays previous daily searches.
- The user can open a paper detail page.
- Idea maps use cached arXiv HTML when available.
- Claims expand into warrants.
- Clicking a warrant jumps to cited HTML text.
- Tests cover backend units, API flows, worker jobs, frontend states, and opt-in live LLM smoke paths.
