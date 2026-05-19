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
- An OpenRouter API key

### 1. Environment Setup

```bash
cp .env.example .env
# Edit .env and set OPENROUTER_API_KEY
```

### 2. Start Redis, Backend, and Worker

```bash
docker compose up --build
```

This starts:

- Redis on port 6379
- FastAPI on http://localhost:8000 with `uvicorn --reload`
- three RQ workers (one per queue) that restart on Python file changes:
  - `worker-interactive` — feedback, documents, onboarding, scholar import
  - `worker-reports` — daily search and report summary
  - `worker-idea-maps` — idea map generation

Worker process counts are configured in `.env` via `INTERACTIVE_WORKERS`,
`REPORT_WORKERS`, and `IDEA_MAP_WORKERS` (default `1` each).

The Docker dev stack stores SQLite in the `backend_data` Docker volume at
`/workspace/backend/data/paper_search.db`.

### 3. Start the frontend

```bash
cd frontend
pnpm install
pnpm dev
```

Frontend runs at http://localhost:3000 and connects to the API at
http://localhost:8000.

### 4. Sync daily index into SQLite

Pull arXiv and LessWrong date manifests and shards from the public R2 buckets into the app database (required before counts and daily search work):

```bash
scripts/dev-reset
```

`scripts/dev-reset` stops the backend and workers, deletes the SQLite database
from the Docker volume, flushes Redis queue state, runs sync, then starts the app
services again. Re-run this when the published R2 indexes change. HTML for paper
viewing is still fetched from R2 on demand.

### Development commands

```bash
scripts/dev-worker-logs
```

Follows all three worker service logs, hiding Redis, backend, and one-off sync
container output.

```bash
scripts/dev-interrupt-worker
```

Restarts the worker containers to interrupt running worker code, then marks
SQLite jobs that were still `running` as failed so the UI does not show stale
progress.

```bash
scripts/dev-clear-jobs
```

Stops the workers, flushes Redis, marks SQLite jobs that were `queued` or
`running` as failed, then starts the workers again.

```bash
scripts/dev-flush-redis
```

Flushes Redis queue state via the Redis container. No local `redis-cli` install
is required.

### Publish indexes (ingest)

Scrape HTML for a date window, upload to R2, and publish the sharded index. Requires R2 write credentials in `.env`.

```bash
uv run --directory scripts python ingest_arxiv.py --end-date 2026-05-14 --days 7
uv run --directory scripts python ingest_lesswrong.py --end-date 2026-05-14 --days 31 --cookie-file ~/.lesswrong-cookie.txt
uv run --directory scripts python ingest_arxiv.py --step upload-html
```

Flat scripts under `scripts/`: `sync.py`, `r2.py` (shared utils), `ingest_arxiv.py`, `ingest_lesswrong.py`.

### 5. Use the App

1. Open http://localhost:3000
2. Complete onboarding by entering your research interests
3. Review and edit proposed filters, then complete setup
4. Run a daily search from the Daily page
5. Browse matches, open papers, generate idea maps

## Running Tests

### Backend Tests

```bash
cd backend
pytest tests/ -v
```

### Frontend

```bash
cd frontend
pnpm test
```

## Project Structure

```
.
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI route handlers
│   │   ├── db/           # Database session & init
│   │   ├── jobs/         # RQ worker jobs
│   │   ├── llm/          # OpenRouter client & prompts
│   │   ├── models/       # SQLAlchemy models
│   │   ├── schemas/      # Pydantic schemas
│   │   └── services/     # arXiv fetch, HTML parser
│   ├── tests/            # Backend tests
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── app/          # Next.js pages
│   │   ├── components/   # UI components
│   │   ├── hooks/        # React Query hooks
│   │   ├── lib/          # API client
│   │   └── stores/       # Zustand UI state
│   └── package.json
├── docker-compose.yml
├── .env.example
└── impl-plan.md
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check |
| GET | /onboarding/status | Check onboarding completion |
| POST | /onboarding/extractions | Start filter extraction |
| GET | /onboarding/extractions/{id} | Get extraction status |
| POST | /onboarding/complete | Save filters and complete |
| GET | /filters | List all filters |
| POST | /filters | Create a filter |
| PATCH | /filters/{id} | Update a filter |
| POST | /filters/{id}/archive | Archive a filter |
| POST | /filters/{id}/restore | Restore a filter |
| GET | /search-runs | List search history |
| GET | /search-runs/latest | Get latest search run |
| POST | /search-runs/daily | Run daily search |
| GET | /search-runs/{id} | Get search run details |
| GET | /search-runs/{id}/matches | Get search matches |
| GET | /papers/{id} | Get paper details |
| GET | /papers/{id}/html | Get cached paper HTML |
| POST | /papers/{id}/idea-map | Generate idea map |
| GET | /papers/{id}/idea-map | Get idea map |

## LLM Behavior

Daily search requires `OPENROUTER_API_KEY`. Without it, search runs fail with a clear configuration error rather than returning mock matches.

I’m interested in recent machine learning papers about improving factuality and reasoning in language models. I want to track work on retrieval-augmented generation, long-context evaluation, hallucination detection, verification, self-correction, and benchmark design. I’m especially interested in practical methods that improve answer quality or reliability, and less interested in papers focused only on scaling laws or hardware optimization.
