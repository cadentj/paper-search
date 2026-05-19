# Paper Search

A single-user research paper filtering system that helps researchers keep up with relevant papers through natural language filters, daily searches, and idea maps.

## Stack

- **Backend**: FastAPI, SQLAlchemy, SQLite, Redis, RQ workers
- **Frontend**: Next.js (App Router), React Query, Tailwind CSS, shadcn/ui
- **LLM**: OpenRouter, with model/provider routing in `backend/llm_config.toml`
- **Runtime**: Docker Compose for Redis, FastAPI, and RQ worker; local Next.js dev server

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Node.js 18+ and pnpm
- An [OpenRouter](https://openrouter.ai/) API key

### 1. Environment Setup

```bash
cp .env.example .env
```

Edit `.env` and set:

```
OPENROUTER_API_KEY=sk-or-...
ARXIV_HTML_PUBLIC_BASE_URL=https://pub-0d8457b25cf9489492a59001ba195ea9.r2.dev
LESSWRONG_HTML_PUBLIC_BASE_URL=https://pub-f4bbc499e7764b81bdee40dd67bda9da.r2.dev
```

### 2. Start Redis, Backend, and Workers

```bash
docker compose up --build
```

This starts:

- Redis on port 6379
- FastAPI on http://localhost:8000 with `uvicorn --reload`
- Three RQ workers (one per queue):
  - `worker-interactive` — feedback, documents, onboarding, scholar import
  - `worker-reports` — daily search and report summary
  - `worker-idea-maps` — idea map generation

Worker process counts are configured in `.env` via `INTERACTIVE_WORKERS`,
`REPORT_WORKERS`, and `IDEA_MAP_WORKERS` (default `1` each).

SQLite is stored in the `backend_data` Docker volume at `/workspace/backend/data/paper_search.db`.

### 3. Start the Frontend

```bash
cd frontend
pnpm install
pnpm dev
```

Frontend runs at http://localhost:3000, connecting to the API at http://localhost:8000.

### 4. Sync Daily Index

Pull arXiv and LessWrong date manifests and shards from R2 into the database (required before daily search works):

```bash
scripts/dev-reset
```

This stops the backend, wipes the SQLite database, flushes Redis, runs sync, and restarts. Re-run when the published R2 indexes change.

### 5. Use the App

1. Open http://localhost:3000
2. Complete onboarding — enter research interests or import a Semantic Scholar profile
3. Review and edit proposed filters, then complete setup
4. Run a daily search from the Daily page
5. Browse matches, open papers, generate idea maps

## Development Scripts

| Script | Description |
|--------|-------------|
| `scripts/dev-worker-logs` | Follow worker logs (hides Redis/backend output) |
| `scripts/dev-interrupt-worker` | Restart workers, mark running jobs as failed |
| `scripts/dev-clear-jobs` | Stop workers, flush Redis, fail all active jobs |
| `scripts/dev-flush-redis` | Flush Redis queue state |

## Running Tests

```bash
# Backend
cd backend && uv run pytest tests/ -v

# Frontend
cd frontend && pnpm test
```

## Project Structure

```
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI route handlers
│   │   ├── db/           # Database session & init
│   │   ├── jobs/         # RQ worker jobs
│   │   ├── llm/          # OpenRouter client, prompts, config
│   │   ├── models/       # SQLAlchemy models
│   │   ├── schemas/      # Pydantic schemas
│   │   └── services/     # Business logic layer
│   ├── tests/
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── app/          # Next.js pages
│   │   ├── components/   # UI components
│   │   ├── hooks/        # React Query hooks
│   │   ├── lib/          # API client, utilities
│   │   └── stores/       # Zustand UI state
│   └── package.json
├── scripts/              # Sync, ingest, and dev helper scripts
├── docker-compose.yml
└── .env.example
```

## LLM Behavior

Daily search requires `OPENROUTER_API_KEY`. Without it, search runs fail with a clear configuration error rather than returning mock matches.
