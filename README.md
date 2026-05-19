# Paper Search

Single-user research paper filtering app for daily arXiv/LessWrong discovery, natural-language filters, feedback-driven filter updates, paper notes, and idea maps.

## Stack

- Backend: FastAPI, SQLAlchemy, SQLite, Redis, RQ
- Frontend: Next.js App Router, React Query, Tailwind, shadcn/ui
- LLM: OpenRouter, configured in `backend/llm_config.toml`
- Data: public R2 indexes synced into local SQLite

## Setup

Prerequisites: Docker, Node.js 18+, pnpm, uv, and an OpenRouter API key.

```bash
cp .env.example .env
```

Set these in `.env`:

```bash
OPENROUTER_API_KEY=sk-or-...
ARXIV_HTML_PUBLIC_BASE_URL=https://pub-0d8457b25cf9489492a59001ba195ea9.r2.dev
LESSWRONG_HTML_PUBLIC_BASE_URL=https://pub-f4bbc499e7764b81bdee40dd67bda9da.r2.dev
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Install dependencies:

```bash
uv sync
cd frontend && pnpm install && cd ..
```

Sync papers into a fresh database before running daily search:

```bash
scripts/dev-reset
```

`dev-reset` starts Redis, stops app services, clears the Docker SQLite volume and Redis queues, runs the R2 sync, then restarts the backend and workers.

Start or restart the backend stack without resetting data:

```bash
docker compose up --build
```

Run the frontend:

```bash
cd frontend
pnpm dev
```

Open http://localhost:3000. The API runs at http://localhost:8000.

## Development

Useful scripts:

| Command | Purpose |
| --- | --- |
| `scripts/dev-worker-logs` | Follow worker logs |
| `scripts/dev-interrupt-worker` | Restart workers and fail running jobs |
| `scripts/dev-clear-jobs` | Stop workers, flush Redis, fail active jobs |
| `scripts/dev-flush-redis` | Flush Redis queue state |

Run checks:

```bash
uv run ruff check backend core scripts
uv run pytest backend/tests -q

cd frontend
pnpm lint
pnpm test -- --run
```

## Project Layout

```text
backend/app/      FastAPI routes, services, models, jobs, LLM client
core/             Shared paper models, date windows, R2 record helpers
frontend/src/     Next.js app, components, hooks, API client
scripts/          R2 sync/ingest and local development helpers
docker-compose.yml
```

## Notes

- Daily search and summaries require `OPENROUTER_API_KEY`; missing keys fail explicitly.
- `scripts/sync.py` refuses to import into a non-empty paper table. Use `scripts/dev-reset` for a clean Docker-backed sync.
- Worker queues are split by job kind: interactive jobs, daily reports, and idea maps.
