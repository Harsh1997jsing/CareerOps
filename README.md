# CareerOps

Human-approval job application assistant. It scores jobs against your real
skills/evidence, generates a resume and cover letter from that evidence,
validates every claim and the document's ATS-compatibility, and tracks
applications — but you always click submit yourself, in your own browser.

All six originally planned phases are built (see `memory/` for what was
built in each phase and why, and `memory/known-gaps.md` for what's still
missing before this runs end-to-end — there's no orchestration wiring the
phases together yet, and it hasn't been run against a live Postgres or with
LibreOffice installed).

## Setup

```bash
python3.12 -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# edit .env: ANTHROPIC_API_KEY, JWT_SECRET_KEY, DEFAULT_ADMIN_PASSWORD are
# all required — the app fails fast at startup if any are unset (generate
# a secret with: python -c "import secrets; print(secrets.token_urlsafe(48))")

docker compose up -d          # starts Postgres
alembic upgrade head          # applies migrations/ — app/models/ is the schema's
                               # source of truth, this is how it reaches Postgres
```

The ATS validator additionally needs [LibreOffice](https://www.libreoffice.org/)
installed (it uses the `soffice` command headless) to convert a generated
DOCX to PDF for the round-trip check.

## Fill in your data

Edit these before running anything — the system is only as accurate as
what's in here:

- `data/profile.yaml`
- `data/skills.yaml`
- `data/constraints.yaml`
- `data/evidence.yaml`
- `data/voice_samples/` — drop 3-5 samples of your own past writing
  (`.txt`/`.md` files) in here before generating a cover letter; it's used
  only as a tone/style reference, never copied for content.

## Run tests (no API key or database needed — everything's mocked)

```bash
pytest tests/ -v
```

One test is skipped unless LibreOffice is installed
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
(LinkedIn, in any form, from all three).

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

**3. MCP explore** (live search against JOBO / Indeed-HasData, for the
frontend's Explore page — needs `JOBO_MCP_API_KEY`/`HASDATA_*` set in
`.env`; not persisted to `jobs` unless explicitly saved):

```python
import asyncio
from app.sources.mcp.explore import search

jobs = asyncio.run(search("backend engineer", {"location": "Bangalore"}))
```

## Run the API Server (needs Postgres reachable via `DATABASE_URL`)

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

Backs `../frontend` (a React app — see its README, not yet scaffolded) over
17 routes: `/health` (unauthenticated), auth/login/users/tenants, list/review
jobs (paginated), approve/reject, open a posting, mark applied, and the MCP
explore search. Every route except `/health` and `/auth/login` requires a
bearer token; `/auth/login` is rate limited (5 attempts / 5 min / client+email).
`GET /docs` has the live OpenAPI schema. CORS is open to `FRONTEND_ORIGIN`
(`.env`, defaults to `http://localhost:5173`).

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
scrape, MCP explore), a real SQLAlchemy ORM (`app/models/`) with Alembic
migrations, and an async FastAPI layer (`app/api/`, 17 routes incl.
multi-tenant JWT auth, every route but `/health`/`/auth/login` requiring a
bearer token — see `memory/api.md`'s "Backend audit fixes" section) for a
separate frontend (`../frontend/README.md`, not yet scaffolded — there is
currently no working review UI, see `memory/known-gaps.md`). 175 tests
passing, 1 skipped pending a local LibreOffice install.

See `memory/known-gaps.md` for what's genuinely still missing (mainly: an
orchestrator to run the phases as one pipeline, real data in place of the
placeholder YAML files, and verification against a live Postgres instance —
every DB-touching test runs against a real aiosqlite in-memory session now,
which is meaningfully stronger than mocking, but Postgres itself is still
unverified).
