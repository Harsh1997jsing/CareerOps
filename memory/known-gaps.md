# Known gaps

Everything below is real, not hypothetical — read this before assuming the
pipeline works end-to-end just because all phases are "built."

## Auth gates access, not tenant data (backend audit finding F2)

`/jobs`, `/applications/*`, `/explore/*` now require a valid bearer token
(fixed: backend audit finding F1), but `Job`/`JobAnalysis`/`Application`/
`GeneratedDocument`/`CompanyApplicationHistory` (`app/models/`) carry no
`tenant_id`. Any authenticated user, in any tenant, can read and act on
every job and application — auth answers "who are you," not "which
tenant's data can you see." This is a **deliberate scope boundary for
now**, not an oversight: the rest of the pipeline (ingestion, scoring,
`data/evidence.yaml`, `data/profile.yaml`) has no per-tenant concept
anywhere either — it's one candidate's data, full stop. Adding real
tenant isolation to the job pipeline would mean threading `tenant_id`
through ingestion, scoring, and generation, not just adding a column —
a larger, separate decision than this fix pass covers. If multi-tenant
job data is ever actually wanted, start there, not with a bolt-on filter
on the read routes.

## No orchestration exists

Nothing in this codebase calls "ingest → hard-filter → score → generate
documents → validate → insert into `generated_documents`/`applications` →
review → track" as one pipeline. Each phase's functions work and are
tested in isolation, but there is no script or scheduler (`apscheduler` is
in `requirements.txt` but unused) gluing them together. Building that
orchestration is the largest remaining piece of work.

## Placeholder data

- `data/profile.yaml` still has `"Your Name"`, `you@example.com`, etc.
- `data/evidence.yaml` still has `"Company A"`, `[Your University]`, etc.
- `data/voice_samples/` is empty except an instructional `README.md`.

None of the generation code will produce anything usable until these are
filled in with real information.

## Real infrastructure status (updated after actually running it)

Docker Desktop + WSL2 were installed and the full stack (`db`, `pgadmin`,
`api`, `frontend`, plus a one-off `migrate` service) now runs via
`docker compose up -d --build` — see `README.md`'s "Running with Docker."
What's actually been verified, and what still hasn't:

- **Postgres: verified.** `migrations/versions/278f8db534a1_initial_schema.py`
  ran against a live Postgres 16 container — and this caught a real bug: it
  used a bare `Text()` at three call sites instead of `sa.Text()`, a
  `NameError` that autogenerating against SQLite never exercised (fixed).
  `asyncpg` (runtime) and `psycopg2` (Alembic, `migrations/env.py`) have
  both now connected to real Postgres. `JobAnalysis.strong_matches`/
  `missing_skills`/`risks`'s `JSON().with_variant(JSONB(), "postgresql")`
  has executed its Postgres branch, not just SQLite's.
- **`app/api/main.py` via `uvicorn`: verified against Postgres**, not just
  SQLite — login, JWT issuance, `/jobs`, and `/explore/*` all round-tripped
  through a real container. CORS was found to only allow-list one exact
  origin string (`FRONTEND_ORIGIN`) — `http://localhost:5173` and
  `http://127.0.0.1:5173` are different origins to a browser even though
  they're the same server, so whichever one wasn't configured was silently
  blocked. Fixed in `app/api/main.py`'s `_cors_origins()`, which expands a
  localhost/127.0.0.1 configured origin to include both.
- **`app/sources/mcp/` (JOBO, HasData): HasData verified end-to-end against
  live data**; Jobo confirmed structurally blocked. Testing against real
  servers (not just fixtures) surfaced four real bugs, all fixed:
  - `capabilities.py` picked HasData's `search_tool` by keyword alone,
    which on a 63-tool general-purpose scraping platform (not job-only)
    matched an unrelated Airbnb tool before ever reaching a job tool.
    Fixed: restricted to tools whose own text mentions "job" first.
  - `explore.py`'s query-argument mapping had `"keywords"` (plural) in its
    candidate list; HasData's actual schema uses `"keyword"` (singular),
    so the search term was silently never sent. Fixed: added the singular.
  - `client.py` hardcoded `Authorization: Bearer` for every source.
    HasData's gateway accepts that for `tools/list` but requires the raw
    `x-api-key` header for a real `tools/call` (401 otherwise). Fixed:
    `McpSource.auth_header` in `registry.py` is now per-source.
  - `explore.py`'s result extraction only checked `RESULT_LIST_KEYS` at the
    top level; HasData nests its payload one level inside a `"json"`
    wrapper key (`{"url", "status", "json": {"jobs": [...]}}`), and nests
    `company`/`salary` as objects rather than flat fields. Fixed: added a
    one-level-deep search and object-aware normalization.
  - **Jobo cannot work with a static API key at all**, confirmed against
    [their MCP docs](https://jobo.world/docs/connectors/mcp): the server
    requires a real OAuth 2.1 browser-consent flow ("the first tool call
    opens a Jobo login in your browser... every tool call forwards the
    bearer token your client currently holds"), not the REST quickstart
    key in `.env`. Regenerating the key changes nothing — confirmed with
    two different keys, both failing identically at `tools/call` with an
    OAuth-flavored "access token... may have expired" error while
    `tools/list` and the direct REST API both succeed with the same key.
    `explore.py` already degrades gracefully (Jobo logs a warning and is
    skipped, HasData's results still return) — adding OAuth support is a
    real feature to build (authorization-code flow, token storage,
    refresh), not a config change.
- **Not yet verified:** `ats_validator.convert_docx_to_pdf()`/
  `extract_pdf_text()` (the real DOCX→PDF→text round-trip) — LibreOffice
  still isn't installed on the machine this has been developed on. Install
  it and run `pytest tests/test_ats_validator.py -v` to confirm the
  currently skipped `test_full_ats_roundtrip_with_real_libreoffice` passes.

## Naming mismatch: `missing_requirements` vs `missing_skills`

`JobFitAnalysis.missing_requirements` (the Pydantic field the LLM call in
`job_scorer.py` returns, in `app/llm/schemas.py`) and
`JobAnalysis.missing_skills` (the ORM column, `app/models/job.py`) refer to
the same concept under different names. This is harmless today because
nothing writes a `JobFitAnalysis` into a `JobAnalysis` row yet (see "No
orchestration" above) — but whoever adds that write path will need to
either rename one of them for consistency or map explicitly between the
two field names.

## Review/approve UI still doesn't exist (list + explore UI now does)

`app/dashboard.py` (the Streamlit dashboard) was removed, superseded by
`app/api/` + `../CareerOps-frontend`. The frontend is now scaffolded (React
+ Vite + TypeScript, JWT auth, a sidebar with Dashboard/Explore Jobs/
Target/Job Scraping) and its Dashboard (real `GET /jobs` list, status
filter) and Explore (real `POST /explore/search`, `GET
/explore/capabilities`) pages are wired to live endpoints and verified
working. But there is still **no UI for approving/rejecting a job, viewing
its fit analysis/generated documents side by side, or marking an
application applied** — `JobReview`/`DocumentReview`/`ApproveRejectBar`
from `../CareerOps-frontend/README.md`'s original spec were never built.
Target and Job Scraping are placeholder pages, honestly labeled as such,
since the backend has no HTTP routes for company-target or JobSpy
ingestion (see "No orchestration exists" above — those two sources are
only ever called from a Python REPL today, per `README.md`'s "Try job
ingestion"). The only way to exercise approve/reject/mark-applied today is
`GET /docs` on the running API, `curl`, or an `asyncio.run(...)`-wrapped
Python REPL call into `app/services/applications.py`/`tracker.py` directly.

## Approve vs. Applied are intentionally different states

`POST /applications/{id}/approve` sets `applications.status` to
`"APPROVED"`. Only `POST /applications/{id}/mark-applied` — which calls
`app/services/tracker.py`'s `mark_applied()` with `confirmed=True`
hardcoded in the route itself — sets it to `"APPLIED"`. There is currently
no UI calling either endpoint (see above). Whatever review UI gets built
must keep these as two distinct actions with separate confirmation steps
(see `../CareerOps-frontend/README.md`'s rule 2) — never let "mark applied"
be a side effect of "approve."
