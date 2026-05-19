# Continuing on a different PC

Everything is in GitHub. To resume work on another machine:

## 1. Prereqs

Install on the new PC:

- **Git** — https://git-scm.com/
- **Python 3.11** — https://www.python.org/downloads/release/python-3119/ (any 3.11.x)
- **Node.js 20+** — https://nodejs.org/
- **Claude Code** (if you want me to keep helping) — `npm install -g @anthropic-ai/claude-code`

Optional but useful:

- **Docker Desktop** — only if you want to run Postgres locally for offline dev
- **VS Code** — pick any IDE you like

## 2. Clone the repo

```bash
git clone https://github.com/hellou2xai/LiquorPriceBook.git
cd LiquorPriceBook
```

The repo holds everything: scraper, FastAPI backend, React frontend, Alembic migrations, the
`render.yaml` Blueprint, plus the two sample PDFs and the scraped Excel.

## 3. Set up Python

```bash
# Create a venv so your global Python stays clean
python -m venv .venv

# Activate it
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# Windows cmd:
.\.venv\Scripts\activate.bat
# macOS / Linux:
source .venv/bin/activate

# Install the project in editable mode + dev tools
pip install -e ".[dev]"
```

This installs `lpb_api`, `lpb_core`, `lpb_worker`, and the `templates.NjAllied` scraper as
importable packages.

## 4. Set up Node

```bash
cd web
npm install
cd ..
```

## 5. Local dev workflow (optional)

If you want to run everything locally before pushing changes, you need a Postgres on your
machine. Easiest with Docker:

```bash
docker run -d --name lpb-pg \
  -e POSTGRES_USER=lpb \
  -e POSTGRES_PASSWORD=lpb \
  -e POSTGRES_DB=liquorpricebook \
  -p 5432:5432 \
  postgres:16-alpine
```

Then create a `.env` file at the repo root (already gitignored):

```
DATABASE_URL=postgresql+psycopg://lpb:lpb@localhost:5432/liquorpricebook
APP_ENV=development
WEB_ORIGIN=http://localhost:5173
LPB_ADMIN_USERNAME=admin
LPB_ADMIN_PASSWORD=admin
LPB_ADMIN_TOKEN=local-dev-token
```

Run migrations:

```bash
alembic upgrade head
```

Start the API in one terminal:

```bash
uvicorn lpb_api.main:app --reload --port 8000
```

Start the frontend in another:

```bash
cd web
npm run dev
```

Browse to `http://localhost:5173`, sign in with `admin / admin`. The Vite dev server proxies
`/api` calls to `http://localhost:8000`, so CORS is bypassed.

Ingest a price book locally without going through the UI:

```bash
python -m lpb_worker.jobs.local_ingest "2026-04 Price Book.pdf" --distributor nj-allied
python -m lpb_worker.jobs.local_ingest "2026-05 Price Book.pdf" --distributor nj-allied
```

## 6. Production state on Render

The live deployment is on Render:

| Service | URL | Plan |
|---|---|---|
| `lpb-api` | `https://lpb-api-41nh.onrender.com` | Starter, ~$7/mo |
| `lpb-web` | `https://lpb-web.onrender.com` | Static site, free |
| `lpb-db` | (internal) | Basic-256mb Postgres, ~$7/mo |

Total **~$14/month**.

Custom domain target: `ordering.celr.ai` (web) + `api.ordering.celr.ai` (API). Not yet
attached — when you do attach them in the Render dashboard, also update these env vars:

- `lpb-api` → `WEB_ORIGIN` = `https://ordering.celr.ai`
- `lpb-web` → `VITE_API_URL` = `https://api.ordering.celr.ai` (then manual deploy `lpb-web`)

## 7. Render env vars currently set

| Service | Env var | Notes |
|---|---|---|
| `lpb-api` | `DATABASE_URL` | auto-wired from `lpb-db` |
| `lpb-api` | `APP_ENV` | `production` |
| `lpb-api` | `WEB_ORIGIN` | `https://lpb-web.onrender.com` (update when custom domain attaches) |
| `lpb-api` | `LPB_ADMIN_USERNAME` | `admin` |
| `lpb-api` | `LPB_ADMIN_PASSWORD` | `admin` |
| `lpb-api` | `LPB_ADMIN_TOKEN` | random secret you set; sent back to client on login |
| `lpb-api` | `ANTHROPIC_API_KEY` | (empty for now, fallback heuristic used) |
| `lpb-api` | `RESEND_API_KEY` | (empty for now) |
| `lpb-api` | `SENTRY_DSN` | (empty for now) |
| `lpb-web` | `VITE_API_URL` | `https://lpb-api-41nh.onrender.com` (baked at build) |

If any env var changes, `lpb-api` auto-restarts in ~30s; `lpb-web` needs a manual deploy
because Vite bakes envs into the bundle.

## 8. Day-to-day workflow

1. Edit code locally
2. `pytest tests/ -q` and `ruff check src` to verify
3. `cd web && npm run build` to verify the frontend still builds
4. `git add -A && git commit -m "..." && git push origin main`
5. Render auto-deploys both services on push (~3-5 min)

CI on GitHub Actions runs the test suite + alembic migration + web build on every push, so
the green checkmark on the commit means it's safe to deploy.

## 9. Resume with Claude Code

In this directory, run:

```bash
claude
```

I'll have memory of the architecture decisions (Render stack, Path A scope, the data-quality
quirks of the Allied PDFs) via the memory files at
`~/.claude/projects/<this-dir>/memory/`. The plan file is at
`~/.claude/plans/ancient-dazzling-sunrise.md` — that's the canonical 16-20 week scope.

To start where we left off, mention any of:

- "ingests are stuck pending; debug"
- "wire Fedway / Opici / RNDC scraper templates" (Week 13-19 in the plan)
- "add Clerk for per-retailer accounts" (post-MVP)
- "wire Resend so alerts email out"
- "add AI-B conversational search"

I keep a TaskList for in-flight work; ask `claude` to "show tasks" to see what's open.

## 10. Things to know about the codebase

- **Migrations**: every schema change is a new `alembic/versions/<timestamp>_<slug>.py`. Never
  edit `0001_initial` — it's a frozen SQL snapshot.
- **Revision IDs must be <=32 chars** (Postgres column constraint). Use `NNNN_slug` form
  like `0005_add_thing`. There's a CI guard in `tests/test_alembic_chain.py` that catches
  longer IDs.
- **Every default column needs both `default=` and `server_default=`** so raw SQL inserts
  (alembic seeds, future helpers) get the right value. We learned this the hard way.
- **Static-auth for now**: `admin/admin` is shared across all retailers. Notes and watchlists
  attach to a single default tenant seeded in migration 0004. Real per-retailer auth lands
  when we wire Clerk.
- **Ingest runs in-process** via FastAPI BackgroundTasks; no separate worker service. The
  `src/lpb_worker/` package still exists but is unused on Render until Week 11.

## 11. If the deploy looks broken

- `lpb-api` → **Logs** tab → look for tracebacks at startup or during the most recent ingest
- `lpb-api` → **Events** tab → confirm latest deploy commit matches latest GitHub commit on
  `main`
- `lpb-api` → **Shell** → `alembic current` → should show the latest migration head
- Hit `https://lpb-api-41nh.onrender.com/api/docs` → confirms the API process is alive
- Hit `https://lpb-api-41nh.onrender.com/readyz` → confirms it can reach Postgres
