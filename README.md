# Paper Search

A single-user research paper filtering system that helps researchers keep up with relevant papers through natural language filters, daily searches, and idea maps.

## Stack

- **Backend**: FastAPI, SQLAlchemy, SQLite, Redis, RQ workers
- **Frontend**: Next.js (App Router), React Query, Tailwind CSS, shadcn/ui
- **LLM**: OpenRouter (deepseek/deepseek-v4-flash via novita)
- **Runtime**: Docker Compose (Redis), local backend + frontend

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 18+ and pnpm
- Docker & Docker Compose (for Redis)
- An OpenRouter API key (optional — demo mode works without one)

### 1. Environment Setup

```bash
cp .env.example .env
# Edit .env and set OPENROUTER_API_KEY if you have one
```

### 2. Start Redis

```bash
docker compose up -d
```

This starts Redis on port 6379. If Redis is not available, jobs run in background threads automatically.

### 3. Start Backend

```bash
cd backend
pip install -e ".[dev]"
mkdir -p data
uvicorn app.main:app --reload --port 8000
```

The API runs at http://localhost:8000 with hot-reload enabled.

### 4. Start Frontend

```bash
cd frontend
pnpm install
pnpm dev
```

Frontend runs at http://localhost:3000 and connects to the API at http://localhost:8000.

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

### With live LLM tests (requires API key)

```bash
cd backend
OPENROUTER_API_KEY=your-key RUN_LIVE_LLM_TESTS=1 pytest tests/ -v
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
│   │   ├── core/         # Configuration
│   │   ├── db/           # Database session & init
│   │   ├── jobs/         # RQ worker jobs
│   │   ├── llm/          # OpenRouter client & prompts
│   │   ├── models/       # SQLAlchemy models
│   │   ├── schemas/      # Pydantic schemas
│   │   └── services/     # Mock papers, HTML parser
│   ├── tests/            # Backend tests
│   ├── alembic/          # Database migrations
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
| POST | /feedback | Submit feedback |
| POST | /dev/reset-onboarding | Reset all data (dev only) |

## Demo Mode

When `OPENROUTER_API_KEY` is not set, the app runs in demo mode:
- Onboarding returns pre-built proposed filters
- Daily search returns deterministic mock matches and summaries
- Idea map generation is skipped (no real arXiv HTML to parse)

## Dev Reset

In development mode (`APP_ENV=development`), use the reset button in the sidebar footer to clear all onboarding, filters, search runs, matches, and feedback data.
