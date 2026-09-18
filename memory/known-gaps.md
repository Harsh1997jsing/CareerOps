# Known gaps

Everything below is real, not hypothetical — read this before assuming the
pipeline works end-to-end just because all phases are "built."

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

## Untested against real infrastructure

This was all built in an environment with **no Docker/Postgres** and **no
LibreOffice** available:

- Every DB-touching function (`app/db.py`, `dashboard_data.py`,
  `document_review.py`, `app/sources/common.py`'s `insert_jobs()`,
  `tracker.py`) is tested only against mocked SQLAlchemy engines/
  connections — the actual SQL has never run against real Postgres.
  `list_jobs()`'s `LEFT JOIN LATERAL` in particular is Postgres-specific
  syntax that's only been checked by inspection, not execution. This
  applies equally to `app/api/routes/*.py` — its 16 tests mock the same
  engine, so `uvicorn app.api.main:app` has never actually queried
  Postgres either.
- `ats_validator.convert_docx_to_pdf()`/`extract_pdf_text()` (the real
  DOCX→PDF→text round-trip) have never executed — only the pure structure/
  text-diff sub-functions are tested with fixture data. Install LibreOffice
  and run `pytest tests/test_ats_validator.py -v` to confirm the currently
  skipped `test_full_ats_roundtrip_with_real_libreoffice` passes.
- `app/sources/mcp/` (JOBO, Indeed/HasData) has never connected to a real
  MCP server — `JOBO_MCP_API_KEY`/`HASDATA_*` aren't set anywhere yet.
  `capabilities.py`'s keyword-matching against tool names/schemas and
  `explore.py`'s result-shape parsing (`structured_content` vs. text-JSON
  fallback) are tested only against hand-written fixture `Tool`/
  `CallToolResult` objects — real servers may name their tools/parameters
  differently than the heuristics assume, or nest results under a key
  `RESULT_LIST_KEYS` doesn't cover. Passing tests here only prove the
  logic is internally consistent — once real keys exist, call
  `app.sources.mcp.explore.search()` against the live servers and adjust
  the heuristics to match what actually comes back.
- `app/dashboard.py` has never been opened in an actual browser — only
  exercised via Streamlit's `AppTest` against mocked data.

**Before trusting this for real applications:** run `docker compose up -d`
+ `psql -f schema.sql`, install LibreOffice, fill in real data files, and
manually walk one job through the full pipeline.

## Naming mismatch: `missing_requirements` vs `missing_skills`

`JobFitAnalysis.missing_requirements` (the Pydantic field the LLM call in
`job_scorer.py` returns, in `app/llm/schemas.py`) and
`job_analysis.missing_skills` (the DB column in `schema.sql`) refer to the
same concept under different names. This is harmless today because nothing
writes a `JobFitAnalysis` into `job_analysis` yet (see "No orchestration"
above) — but whoever adds that write path will need to either rename one
of them for consistency or map explicitly between the two field names.

## Dashboard "Approve" vs. tracker "Applied" are intentionally different states

`app/dashboard.py`'s Approve button sets `applications.status` to
`"APPROVED"`. Only `app/services/tracker.py`'s `mark_applied()` — which
requires explicit `confirmed=True` from a human who has actually clicked
submit — sets it to `"APPLIED"`. There is currently no UI wired up to call
`mark_applied()`; it's only reachable by importing and calling it directly
(e.g. from a Python REPL). If a "mark as applied" button in the dashboard
is wanted, it needs its own explicit confirmation step (e.g. a checkbox or
a second click) to preserve the guarantee `mark_applied()` was built
around.
