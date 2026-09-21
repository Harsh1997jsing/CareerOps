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

## Orchestration exists now, but only the review-and-generate half, and only on demand

`POST /jobs/{job_id}/analyze` (hard-filter → score → record) and
`POST /jobs/{job_id}/documents` (generate → write .docx → claim/ATS
validate → get-or-create `Application`) now call that chain for real —
see `app/api/routes/jobs.py`, `app/services/jobs.py`'s `hard_filter_job()`/
`record_analysis()`, and `app/services/document_generator.py`. Both are
user-triggered per job from the frontend's Job Detail page, not automatic.

What's still missing: **ingestion never triggers this automatically.**
`app/sources/mcp/explore.py`'s `search()`, `app/sources/jobspy_source.py`'s
`fetch_jobs()`, and `app/sources/targets.py`'s `search_all()` all still
only stage results for manual review-then-save (`/explore/save`) — nothing
runs hard-filter/score against a job the moment it's saved into `jobs`, so
a saved job sits at `Job.status = "DISCOVERED"` until someone opens its
Job Detail page and clicks Analyze. `apscheduler` (`requirements.txt`) is
still unused — no recurring/scheduled ingestion or scoring run exists.
Automating either of those (auto-analyze on save, or a scheduled ingest+
analyze sweep) is the largest remaining piece of orchestration work.

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

## Naming mismatch: `missing_requirements` vs `missing_skills` — now just a mapping, not a landmine

`JobFitAnalysis.missing_requirements` (the LLM output field,
`app/llm/schemas.py`) and `JobAnalysis.missing_skills` (the ORM column,
`app/models/job.py`) still use different names for the same data — that
part wasn't worth renaming, since `missing_requirements` reads better at
the LLM-prompt layer and `missing_skills` matches `JobListItem`/
`JobDetail`'s existing field name at the API layer. `app/services/jobs.py`'s
`record_analysis()` is now the one place that writes a `JobFitAnalysis`
into a `JobAnalysis` row, and it maps the two names explicitly (with a
comment) — no other write path exists, so there's nothing left to get
this wrong.

## Review/approve UI exists now

`app/dashboard.py` (Streamlit) is still gone, superseded by `app/api/` +
`../CareerOps-frontend`. The frontend's sidebar is now just Dashboard +
AI Search (Explore/Target/Job Scraping stay mounted and routable, just
off the nav — AI Search covers all three of their sources itself). A Job
Detail page (`/jobs/:jobId`) now exists with the fit analysis, an
Analyze/Re-analyze button (`POST /jobs/{id}/analyze`), the generated
documents list with Generate Resume/Generate Cover Letter buttons
(`POST /jobs/{id}/documents`), and the approve/reject/open/mark-applied
bar — gated on `job.application` existing, which it doesn't until a
document has been generated for that job at least once (see
`applications_service.create_application()`'s docstring). Mark-applied
requires an explicit confirm dialog, per CLAUDE.md rule 5.

## Approve vs. Applied are intentionally different states

`POST /applications/{id}/approve` sets `applications.status` to
`"APPROVED"`. Only `POST /applications/{id}/mark-applied` — which calls
`app/services/tracker.py`'s `mark_applied()` with `confirmed=True`
hardcoded in the route itself — sets it to `"APPLIED"`. The Job Detail
page's Approve/Reject/Mark applied buttons keep these as two distinct
actions, per `../CareerOps-frontend/README.md`'s rule 2 — mark-applied
has its own confirm dialog and is never a side effect of approve.

## `Job.status` can be `"REJECT"`, distinct from `"REJECTED"` — a Dashboard filter had the wrong option

`job_scorer.decide()` sets `Job.status` to `"REJECT"` (LLM found the
candidate ineligible) or `POST /jobs/{job_id}/analyze` sets it directly
to the same `"REJECT"` when `hard_filter_job()` fails first — both
distinct from `"REJECTED"`, which only `POST /jobs/{job_id}/reject` (the
Dashboard's manual hide action) sets. The Dashboard's status filter
dropdown previously offered `"APPROVED"` as an option, which is never a
valid `Job.status` value at all (it's an `Application.status` value) —
fixed to offer `DISCOVERED`/`READY_FOR_REVIEW`/`REVIEW_REQUIRED`/
`REJECT`/`REJECTED` instead.

## `data/profile.yaml`/`data/evidence.yaml` are still placeholder data, and `data/voice_samples/` is still empty

Confirmed still true as of this note: `data/profile.yaml` still has
`"Your Name"`/`you@example.com`, `data/evidence.yaml` still has
`"Company A"`, and `data/voice_samples/` has nothing but its own
instructional `README.md`. Resume generation runs fine against
placeholder data (it just produces a resume for "Your Name"), but
`app/services/cover_letter.py`'s `generate_cover_letter()` calls
`load_voice_samples()`, which **raises `NoVoiceSamplesError`** when the
directory has no real `.txt`/`.md` samples — `POST /jobs/{id}/documents`
with `type: "cover_letter"` will fail until at least one real writing
sample is added. Nothing automated can fill these in; they're the
candidate's own identity, evidence, and writing voice.
