# Phase 5: Job ingestion (Greenhouse + Lever)

## What's there

- `app/sources/common.py` — shared by both adapters:
  - `normalize_location()` — maps free-text API strings ("Bengaluru,
    Karnataka", "Remote - India") onto the exact canonical names
    `data/constraints.yaml`'s `allowed_locations` uses. Anything
    unrecognized passes through unchanged rather than being guessed at, so
    it correctly fails the location hard filter instead of silently
    matching something wrong.
  - `normalize_employment_type()` — same idea for Full-time/Part-time/
    Contract/Internship variants.
  - `description_hash()` — SHA-256 of whitespace-normalized, lowercased
    description text, matching `jobs.description_hash`.
  - `insert_jobs()` — inserts one row at a time with
    `ON CONFLICT (description_hash) DO NOTHING`. Deliberately not a bulk
    executemany — DBAPI `rowcount` behavior on bulk inserts is unreliable
    across drivers, and with `MAX_JOBS_PER_RUN = 50` the per-row round trip
    cost doesn't matter.
- `app/sources/greenhouse.py` / `lever.py` — call only each board's public,
  unauthenticated JSON API (`boards-api.greenhouse.io`,
  `api.lever.co`) — the same JSON a company's own careers page fetches
  client-side. No scraping, no browser automation, no LinkedIn.

## Decisions worth knowing

- **Greenhouse has no reliable employment-type field** in its base API.
  `_find_employment_type()` searches a job's `metadata` list for a field
  named like "Employment Type" and leaves it `None` if not found, rather
  than assuming every posting is full-time — a false "Full-time" default
  risked letting an unwanted contract role slip through the hard filter.
  Lever exposes this reliably via `categories.commitment`.
- `posted_at` is parsed into a real `datetime` from each source's native
  format (ISO8601 for Greenhouse, epoch-milliseconds for Lever), not left
  as a raw string.
- `requests>=2.31` was added to `requirements.txt` as an explicit
  dependency — it was already present transitively (via some other
  package) but wasn't declared directly before this phase.

## Testing

All HTTP calls mocked via `unittest.mock.patch` on `requests.get`; no
network access needed to run the tests. `insert_jobs()` tested against a
mocked engine.
