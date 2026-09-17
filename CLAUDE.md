# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

CareerOps is a job application assistant with **mandatory human approval before
any submission**. It scores jobs against a candidate's real skills/evidence,
generates a resume and cover letter from that evidence, validates every
generated claim and the document's ATS-compatibility, and tracks applications
— but a human always clicks submit, in their own browser. Phases 0–6 (the
full originally planned scope) are built. See `memory/` for what was built in
each phase, why, and what's still missing before this works end-to-end.

## Hard rules

These constrain every change in this repo, not just the phase they were
written for:

1. **Never write code that auto-submits an application on any external
   platform.** Every application ends at "ready for human review" — the user
   clicks submit themselves. `app/services/tracker.py`'s `open_job_url()`
   only opens a browser tab; it never fills in or submits a form.
2. **Never write browser automation that spoofs fingerprints, evades bot
   detection, or scrapes LinkedIn.** Job ingestion (`app/sources/`) only
   calls public, unauthenticated job-board JSON APIs (Greenhouse, Lever). If
   a source needs more than its public API, flag it instead of building
   around it.
3. **Every factual claim in a generated resume/cover letter/screening answer
   must trace to an `evidence_id` from `data/evidence.yaml`.** No matching
   evidence id means the claim gets blocked by `claim_validator.py`, not
   softened or reworded around.
4. **Use `os.environ["ANTHROPIC_MODEL"]` everywhere — never hardcode a model
   string.** All LLM calls go through `app/llm/anthropic_client.py`'s
   `structured_call()`, which is the only place that reads this env var.
5. **`mark_applied()` in `tracker.py` requires `confirmed=True` with no
   default** — it must never be called without the human explicitly
   confirming they manually submitted the application themselves.

## Setup and commands

```bash
python3.12 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env             # then fill in ANTHROPIC_API_KEY

docker compose up -d             # starts Postgres
psql postgresql://careerops:careerops@localhost:5432/careerops -f schema.sql
```

Run the full test suite (no API key needed — every LLM/DB call is mocked):
```bash
pytest tests/ -v
```

Run a single test file or test:
```bash
pytest tests/test_hard_filters.py -v
pytest tests/test_hard_filters.py::test_fails_on_disallowed_location -v
```

One test (`test_full_ats_roundtrip_with_real_libreoffice` in
`tests/test_ats_validator.py`) is skipped unless LibreOffice (`soffice`) is
on PATH — install it to actually exercise the DOCX→PDF round-trip.

Run the dashboard (needs `DATABASE_URL` reachable — see Postgres setup above):
```bash
streamlit run app/dashboard.py
```

There is no lint/format command configured yet.

## Data files (edit before running anything)

The system's output is only as good as what's filled in here — these are hand-edited,
not generated:

- `data/profile.yaml` — candidate profile (still placeholder values as of this writing)
- `data/skills.yaml` — candidate skills
- `data/constraints.yaml` — hard filter rules (allowed locations, employment types,
  experience ceiling, excluded keywords, company cooldown days)
- `data/evidence.yaml` — every factual claim the candidate can make, each with a
  stable `id` (e.g. `EXP001`, `PROJ004`). This ID is the join key the claim
  checker uses — nothing should ever appear in a generated resume/cover
  letter that isn't traceable back to an evidence ID here. (Still placeholder
  values as of this writing.)
- `data/voice_samples/*.txt`/`*.md` — 3-5 samples of the candidate's own past
  writing, used only as a style/tone reference for cover-letter generation.
  Currently empty except for an instructional `README.md` (which the loader
  skips by name).

## Architecture

**Pipeline order, enforced by module boundaries more than by any orchestrator
(there isn't one yet — see `memory/known-gaps.md`):**

1. `app/sources/greenhouse.py` / `lever.py` — pull up to 50 postings per run
   from each board's public JSON API, normalize fields (via
   `app/sources/common.py`) onto the vocabulary `hard_filters.py` expects,
   hash the description for dedupe, and insert into `jobs` with
   `ON CONFLICT (description_hash) DO NOTHING`.
2. `app/services/hard_filters.py` — deterministic, non-LLM checks
   (`check_hard_filters`, `check_company_cooldown`). Only jobs that pass
   these should ever reach the scorer.
3. `app/services/job_scorer.py` — `score_job()` calls Claude for a
   `JobFitAnalysis`; `decide()` turns it into `REJECT` / `REVIEW_REQUIRED` /
   `READY_FOR_REVIEW` — never a single fit-score threshold; low confidence or
   any listed risk forces `REVIEW_REQUIRED` regardless of score.
4. `app/services/resume_generator.py` / `cover_letter.py` — generate DOCX
   documents (via shared `app/services/docx_writer.py`) strictly from
   `data/evidence.yaml` and `data/skills.yaml`/`data/profile.yaml`, never
   from a previously generated document.
5. `app/services/claim_validator.py` / `ats_validator.py`, gated through
   `app/services/document_review.py` — the only code path allowed to set
   `generated_documents.claim_check_passed`/`ats_check_passed`.
6. `app/dashboard.py` (Streamlit UI) + `app/services/dashboard_data.py` (its
   DB layer) — human reviews fit/matches/gaps and generated documents next
   to evidence, and Approve/Reject sets `applications.status` to
   `APPROVED`/`REJECTED`. This is **not** the same as `APPLIED` — see next.
7. `app/services/tracker.py` — `open_job_url()` opens the posting for manual
   application; `mark_applied()` is the only path to `applications.status =
   APPLIED`, requires explicit `confirmed=True`, and upserts
   `company_application_history` in the same transaction.

**LLM access is centralized in `app/llm/`:**
- `anthropic_client.py` — the *only* place that should construct an `Anthropic()`
  client or call the SDK directly. `structured_call(prompt, output_schema)` wraps
  `client.messages.parse(output_format=...)` so callers get back a validated
  Pydantic instance instead of hand-parsed JSON. It raises on API failure by
  design — callers must catch and log, never silently swallow a failed call.
- `schemas.py` — every LLM call's output shape, as Pydantic models
  (`JobFitAnalysis`, `ScreeningAnswer`, `ClaimCheckResult`,
  `GeneratedResumeSection`, `GeneratedCoverLetter`). Add new schemas here
  when adding a new LLM call.
- `prompts.py` — one prompt template per LLM call, as plain `.format()`
  strings (`JOB_FIT_ANALYSIS_PROMPT`, `RESUME_SECTION_PROMPT`,
  `COVER_LETTER_PROMPT`, `CLAIM_CHECK_PROMPT`). All of them explicitly
  instruct the model not to invent skills/experience beyond the evidence
  YAML, and the claim checker prompt is deliberately strict: an unverified
  claim blocks the application even if it looks plausible.

**Deterministic guards (not LLM calls) worth knowing about:**
- `resume_generator.check_keyword_density()` flags resume sections that
  mirror 6+ consecutive words from the job description verbatim — short
  overlaps (a skill name) are expected and ignored; this is a warning
  surfaced to the human, not a hard block (unlike claim validation).
- `ats_validator.check_docx_structure()` flags tables, inline images, text
  boxes (found via raw XML — python-docx doesn't model them), and
  multi-column sections (via the `w:cols/@w:num` XML attribute — python-docx
  has no public API for column count).

**Database (`schema.sql`):** run once by hand to bootstrap Postgres; the
comment at the top says to switch to Alembic migrations
(`alembic init migrations`) once past the POC stage. Tables: `jobs`,
`job_analysis`, `evidence`, `generated_documents`, `applications`,
`company_application_history`. All DB access goes through
`app/db.py:get_engine()` (a cached SQLAlchemy engine reading
`DATABASE_URL`) — no module should construct its own engine.

Known naming mismatch worth checking before relying on it:
`JobFitAnalysis.missing_requirements` (the LLM output field in
`schemas.py`) vs `job_analysis.missing_skills` (the DB column in
`schema.sql`) refer to the same concept under different names. Nothing
currently writes a `JobFitAnalysis` into `job_analysis`, so this hasn't
caused a bug yet — but whoever adds that write path needs to map one to the
other explicitly. See `memory/known-gaps.md`.

## Known repo quirk

There is a stray, empty directory in the repo root literally named
`{app/api,app/services,app/llm,app/sources,app/models,data,tests,documents,generated}`
— the artifact of a `mkdir {a,b,c}` brace-expansion that was run in a shell without
brace expansion support. It is not part of the project structure; don't create files
inside it.
