# CareerOps

Human-approval job application assistant. It scores jobs against your real
skills/evidence, generates a resume and cover letter from that evidence,
validates every claim and the document's ATS-compatibility, and tracks
applications — but you always click submit yourself, in your own browser.

All six originally planned phases are built (see `memory/` for what was
built in each phase and why, and `memory/known-gaps.md` for what's still
missing before this runs end-to-end — there's no orchestrator wiring the
phases together yet). The API, migrations, and full Docker stack (Postgres +
pgAdmin + the API itself) have been run and verified end-to-end against a
real Postgres instance.

## Prerequisites

- **Docker Desktop** (with the WSL2 backend, on Windows) — runs Postgres,
  pgAdmin, and optionally the API itself. See "Running with Docker" below.
- **Python 3.12** — only needed if you run the API on the host instead of
  in a container (see "Local development" below).
- **[LibreOffice](https://www.libreoffice.org/)** (optional) — the ATS
  validator uses the `soffice` command headless to convert a generated DOCX
  to PDF for the round-trip check. One test is skipped without it.

## Setup

```bash
git clone <this repo>
cd careerops

cp .env.example .env
# edit .env — ANTHROPIC_API_KEY, JWT_SECRET_KEY, DEFAULT_ADMIN_PASSWORD are
# all required, no code-level default (the app fails fast at startup if any
# are unset). Generate a JWT secret with:
#   python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Then either run everything in Docker, or run Postgres/pgAdmin in Docker and
the API on your host — see the two options below.

### Option A — fully Dockerized (frontend + API + Postgres + pgAdmin)

```bash
docker compose up -d --build
```

That's the entire setup — one command. `docker-compose.yml` wires up the
full dependency chain: `db` starts and must pass its healthcheck before
anything else proceeds; a one-off `migrate` service then runs `alembic
upgrade head` and exits; `api` only starts once both `db` is healthy and
`migrate` exited successfully, and has its own healthcheck (`GET /health`);
`frontend` only starts once `api` is healthy. No separate migration command
needed anymore — re-running `docker compose up -d` is safe any time (the
`migrate` step is idempotent) and picks up any new migration automatically.

The API container reaches Postgres over the compose network as `db:5432`;
`docker-compose.yml`'s `api`/`migrate` services override `DATABASE_URL` for
this — you don't need to edit `.env` for it. The `frontend` service
(defined here, but built from `../CareerOps-frontend`) runs the Vite dev
server with the project's source bind-mounted in, so edits on the host
hot-reload inside the container — see `../CareerOps-frontend/Dockerfile`
for details. Every service has `restart: unless-stopped`, so a Docker
Desktop restart brings them all back without a manual `docker compose up`.

### Option B — local development (API on host, Postgres/pgAdmin in Docker)

```bash
python3.12 -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt

docker compose up -d db pgadmin           # starts only Postgres + pgAdmin
alembic upgrade head                      # applies migrations/ — app/models/ is the schema's
                                           # source of truth, this is how it reaches Postgres
uvicorn app.api.main:app --reload
```

Here `DATABASE_URL` in `.env` is used as-is (`localhost:<port>`, see the
port note below).

### A note on the Postgres port

`docker-compose.yml` maps Postgres to **host port 5433** (container port
stays 5432) because host port 5432 is commonly already taken by a native
PostgreSQL install. `.env`'s `DATABASE_URL` must use whatever host port
`docker-compose.yml` actually maps — if your machine has no conflict on
5432, change both the `db` service's `ports:` entry and `.env`'s
`DATABASE_URL` back to 5432.

## Running with Docker — command reference

```bash
# Start everything (db + migrate + pgadmin + api + frontend), building images first
docker compose up -d --build

# Start only specific services (e.g. skip frontend/api for backend-only work)
docker compose up -d db pgadmin
docker compose up -d db migrate pgadmin api

# Re-run migrations on demand (e.g. to check migrate's own logs)
docker compose up migrate

# See what's running (migrate shows "Exited (0)" once done — that's success, not a crash)
docker compose ps -a

# Follow logs for one service (or omit the name for all of them)
docker compose logs -f api
docker compose logs -f frontend

# Rebuild just one image after a dependency/code change, then restart it
docker compose up -d --build api
docker compose up -d --build frontend

# Restart a single service without rebuilding
docker compose restart api

# Stop everything (containers removed, named volumes — and their data — kept)
docker compose down

# Stop everything AND delete the named volumes (wipes the Postgres data!)
docker compose down -v

# Open a psql shell inside the running db container
docker compose exec db psql -U careerops -d careerops
```

The `frontend` container only needs rebuilding (`--build`) after a
`package.json` change — plain source edits hot-reload through the bind
mount without a rebuild.

### pgAdmin

Open **http://localhost:5050** and log in with `PGADMIN_DEFAULT_EMAIL` /
`PGADMIN_DEFAULT_PASSWORD` from `docker-compose.yml` (defaults:
`admin@careerops.dev` / `careerops`).

To register the `db` container as a server inside pgAdmin, use **`db`** as
the host (pgAdmin reaches it over the compose network, not `localhost`) and
port **5432** (the container's internal port, not the host-mapped 5433):

- Host: `db`
- Port: `5432`
- Database: `careerops`
- Username / Password: `careerops` / `careerops`

## Fill in your data

Edit these before running anything — the system is only as accurate as
what's in here:

- `data/profile.yaml`
- `data/skills.yaml`
- `data/constraints.yaml`
- `data/evidence.yaml`
- `data/companies.yaml` — Greenhouse/Lever board tokens for manual ingestion
- `data/voice_samples/` — drop 3-5 samples of your own past writing
  (`.txt`/`.md` files) in here before generating a cover letter; it's used
  only as a tone/style reference, never copied for content.

## Run tests (no API key or database needed — everything's mocked)

```bash
pytest tests/ -v
```

174 passing, 1 skipped unless LibreOffice is installed
(`test_full_ats_roundtrip_with_real_libreoffice`).

## Try the job scorer (needs `ANTHROPIC_API_KEY` set)

```python
from app.services.job_scorer import score_job, decide

analysis = score_job(
    job_description="We need a Python engineer with FastAPI and AWS experience...",
    skills_path="data/skills.yaml",
    evidence_path="data/evidence.yaml",
    constraints_path="data/constraints.yaml",
)
print(analysis)
print(decide(analysis))
```

## Try the resume + cover letter generator (needs `ANTHROPIC_API_KEY` set)

```python
from app.services.resume_generator import generate_resume
from app.services.cover_letter import generate_cover_letter
from app.services.docx_writer import write_resume_docx, write_cover_letter_docx
import yaml

job_description = "We need a Python engineer with FastAPI and AWS experience..."
profile = yaml.safe_load(open("data/profile.yaml"))

resume = generate_resume(job_description, "data/skills.yaml", "data/evidence.yaml")
print(resume.keyword_density_warnings)  # sections that mirror the JD too closely
write_resume_docx(profile, resume.sections, "generated/resume.docx")

cover_letter = generate_cover_letter(job_description, "data/evidence.yaml", "data/profile.yaml")
print(cover_letter.word_count, cover_letter.word_count_warning)
write_cover_letter_docx(profile, cover_letter.content, "generated/cover_letter.docx")
```

## Try job ingestion

Three independent source paths — see `CLAUDE.md`'s Architecture section
for how they fit together, and rule 2 for what's deliberately excluded
(LinkedIn, in any form, from all three; Naukri additionally excluded from
the MCP explore path).

**1. Manual company targets** (Greenhouse / Lever public APIs, no auth needed):

```python
import asyncio
from app.core.database import get_session_factory
from app.sources.targets import ingest_all

# edit data/companies.yaml with real board tokens / company slugs first
async def main():
    async with get_session_factory()() as session:
        return await ingest_all(session)

inserted = asyncio.run(main())
```

Or call a single board directly:

```python
from app.sources.greenhouse import fetch_jobs as fetch_greenhouse_jobs
from app.sources.lever import fetch_jobs as fetch_lever_jobs

jobs = fetch_greenhouse_jobs(board_token="some-company", company="Some Company")
# or: fetch_lever_jobs(company_slug="some-company", company="Some Company")
```

Capped at 50 jobs per run per adapter. `fetch_jobs()` itself stays sync
(plain `requests` calls); only the DB write is async. Pass an `AsyncSession`
(see `app/core/database.py:get_session_factory()`) to
`await app.sources.common.insert_jobs(session, jobs)` to dedupe and store them.

**2. Multi-site scrape** (Glassdoor, Naukri, Indeed, ZipRecruiter, Google —
via the `JobSpy` library; LinkedIn is hardcoded out of every call):

```python
from app.sources.jobspy_source import fetch_jobs

jobs = fetch_jobs(search_term="backend engineer", location="Bangalore")
```

**3. MCP explore** (live search against JOBO / HasData's Glassdoor+Indeed
tools, for the frontend's Explore page; not persisted to `jobs` unless
explicitly saved):

```python
import asyncio
from app.sources.mcp.explore import search

jobs = asyncio.run(search("backend engineer", {"location": "Bangalore"}))
```

**HasData is verified working end-to-end** with `HASDATA_MCP_API_KEY` set —
confirmed against live data (real Glassdoor/Indeed job listings returned).
It authenticates via the `x-api-key` header, not `Authorization: Bearer`
(`McpSource.auth_header` in `registry.py` — its gateway accepts Bearer for
listing tools but rejects it at actual tool-call time).

**JOBO_MCP_API_KEY alone will never work**, no matter its value — Jobo's
MCP server requires a real OAuth 2.1 browser-consent flow per
[their docs](https://jobo.world/docs/connectors/mcp) ("the first tool call
opens a Jobo login in your browser"), not a static API key. This backend
doesn't implement an OAuth client, so `explore.py` logs a warning and
skips Jobo rather than failing the whole search — HasData's results still
return normally. Adding OAuth support is a real feature to build, not a
config change; see `memory/known-gaps.md`.

## Run the API Server (needs Postgres reachable via `DATABASE_URL`)

Either run it in Docker (see "Running with Docker" above) or on the host:

```bash
uvicorn app.api.main:app --reload
```

The FastAPI REST API provides read-heavy endpoints for jobs, applications,
and MCP exploration, complete multi-tenant stateless JWT authentication,
and powers the React frontend interface. Every route and every DB-touching
service function is `async` (SQLAlchemy's async engine — `asyncpg` for
Postgres, `aiosqlite` for a `sqlite:///` `DATABASE_URL`); see
`memory/api.md` for the full endpoint inventory and `CLAUDE.md`'s
Architecture section for how the async layer is wired.

Backs `../CareerOps-frontend` (a React app — see its own README, not yet
scaffolded) over 17 routes: `/health` (unauthenticated), auth/login/users/
tenants, list/review jobs (paginated), approve/reject, open a posting, mark
applied, and the MCP explore search. Every route except `/health` and
`/auth/login` requires a bearer token; `/auth/login` is rate limited (5
attempts / 5 min / client+email). `GET /docs` has the live OpenAPI schema.
CORS is open to `FRONTEND_ORIGIN` (`.env`, defaults to
`http://localhost:5173`).

## Marking an application as actually submitted

After you've manually submitted an application in your own browser:

```python
import asyncio
from app.services.tracker import mark_applied
from app.core.database import get_session_factory

async def main():
    async with get_session_factory()() as session:
        await mark_applied(session, application_id=1, job_id=1, company="Some Company", confirmed=True)

asyncio.run(main())
```

`confirmed=True` is required with no default — this is the only way
`applications.status` becomes `APPLIED`, and nothing in this codebase ever
submits an application on your behalf.

## What's built

All 6 phases: hard filters + company cooldown, job scorer, resume/cover
letter generation with a keyword-density guard, claim + ATS validation
gating `generated_documents`, and manual-submit tracking — plus three
ingestion source paths (manual Greenhouse/Lever targets, JobSpy multi-site
scrape, MCP explore — HasData's Glassdoor/Indeed tools verified against
live data, Jobo blocked on OAuth support this backend doesn't have yet),
a real SQLAlchemy ORM (`app/models/`) with Alembic migrations verified
against a live Postgres instance, and an async FastAPI layer (`app/api/`,
17 routes incl. multi-tenant JWT auth, every route but `/health`/
`/auth/login` requiring a bearer token — see `memory/api.md`'s "Backend
audit fixes" section) for a separate frontend (`../CareerOps-frontend` —
React + Vite + TypeScript, scaffolded with a sidebar (Dashboard/Explore
Jobs/Target/Job Scraping), JWT auth, and the Dashboard and Explore pages
wired to real endpoints; Target and Job Scraping are placeholders since
the backend has no HTTP routes for company-target or JobSpy ingestion yet
— see its own `README.md`/`CONTRACT.md` and `memory/known-gaps.md`).

A `Dockerfile` and `docker-compose.yml` run the frontend, API, Postgres,
pgAdmin, and a one-off migration step as containers with a real dependency
chain (db healthy → migrate → api healthy → frontend) and
`restart: unless-stopped` on every long-running service — see "Running
with Docker" above. 174 tests passing, 1 skipped pending a local
LibreOffice install.

See `memory/known-gaps.md` for what's genuinely still missing (mainly: an
orchestrator to run the phases as one pipeline, real data in place of the
placeholder YAML files, and OAuth support for Jobo's MCP connector).
