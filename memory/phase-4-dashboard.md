# Phase 4: Streamlit dashboard

## What's there

- `app/services/dashboard_data.py` — all DB access for the dashboard, kept
  separate from the Streamlit UI so it's unit-testable without a live
  Postgres or Streamlit session:
  - `list_jobs()` — jobs LEFT JOIN LATERAL'd to their latest `job_analysis`
    row, mapped to `JobListItem`.
  - `list_generated_documents()`, `get_application_for_job()`.
  - `check_cooldown_for_company()` — pulls `company_application_history`
    and **reuses `hard_filters.check_company_cooldown()`** rather than
    reimplementing the cooldown math, so the dashboard's warning and the
    pre-scoring hard filter can never disagree.
  - `approve_application()` / `reject_application()` — the only code paths
    that write `applications.status`.
- `app/dashboard.py` — thin Streamlit UI: sidebar status filter, one
  expander per job (fit score/confidence/matches/gaps), cooldown warning,
  generated-document previews (read via `python-docx`) next to
  `data/evidence.yaml`, Approve/Reject buttons.

## Decisions worth knowing

- **Approve sets `applications.status` to `"APPROVED"`, not `"APPLIED"`.**
  The original Phase 6 spec is explicit that `APPLIED` should only be set
  after the human manually confirms they've submitted — so "Approve" here
  means "I've reviewed this package, it's good to go," and the actual
  `APPLIED` transition is Phase 6's `tracker.mark_applied()`, gated on
  explicit confirmation. If this dashboard's Approve button is ever meant
  to directly mean "I applied," that's a deliberate departure from what
  was asked and should be revisited.
- This dashboard reads `applications`/`generated_documents` rows that
  **nothing in the codebase creates yet** — see `known-gaps.md`.

## Testing

- `test_dashboard_data.py` — pure row-mapping functions tested directly;
  SQL-issuing functions tested against a mocked SQLAlchemy engine
  (asserting the query executed and its params, not real DB semantics).
- `test_dashboard.py` — 5 tests using Streamlit's `AppTest` (from
  `streamlit.testing.v1`), which actually executes `app/dashboard.py`'s
  real render logic end-to-end against mocked `dashboard_data` functions:
  job card rendering, cooldown warning display, generated-document
  listing, and clicking Approve through to `approve_application()` being
  called. `AppTest.from_file()` resolves relative paths against the
  *calling test file's* directory, not the repo root — use an absolute
  path. First script run in a session pays Streamlit's module cold-start
  cost past the 3s default timeout — `default_timeout=15` was used to
  avoid a flaky first-test failure.
- No live Postgres was available while building this, so nothing here has
  been checked against a real database or run in an actual browser — the
  `AppTest` smoke tests are the closest verification available in this
  environment.
