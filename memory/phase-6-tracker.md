# Phase 6: Application tracker

## What's there

- `app/services/tracker.py`:
  - `open_job_url()` — a one-line `webbrowser.open()` wrapper. Opens the
    posting in the user's own browser; that's the entire function.
  - `mark_applied()` — the only place `applications.status` becomes
    `"APPLIED"`. `confirmed` is a **required** keyword with no default, so
    it's structurally impossible to call this without deliberately passing
    `confirmed=True`. Passing `False` (or omitting it) raises
    `ApplicationNotConfirmedError` *before* touching the database at all.
    When confirmed, it updates `applications` and upserts
    `company_application_history` in a single transaction, so the cooldown
    tracker can never drift out of sync with an application's actual
    status.

## Decisions worth knowing

- This module has no caller anywhere in the codebase yet — it's meant to
  be invoked manually (e.g. from a Python REPL, or a future CLI/dashboard
  button with an explicit confirmation checkbox) *after* the human has
  actually submitted the application in their browser. Wiring a "confirm
  applied" affordance into `app/dashboard.py` would be the natural next
  step if this needs to be less manual — it wasn't requested as part of
  the original phase list, so it wasn't added.

## Testing

`test_tracker.py` — `webbrowser.open` mocked; `mark_applied()` tested
against a mocked SQLAlchemy engine, including the refusal path (asserting
`engine.begin` is never called when `confirmed=False`).
