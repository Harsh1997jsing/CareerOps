# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

CareerOps is a human-approval job application assistant: it scores jobs against a
candidate's real skills/evidence, and (per the project plan) will eventually generate
resumes/cover letters, validate every generated claim against evidence, check ATS
compatibility, and track applications. This repo is the Phase 0–1 starting point —
most of the architecture described below exists only as a plan, not yet as code.

## Setup and commands

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env             # then fill in ANTHROPIC_API_KEY

docker compose up -d             # starts Postgres
psql postgresql://careerops:careerops@localhost:5432/careerops -f schema.sql
```

Run tests (no API key needed — these only exercise deterministic filters):
```bash
pytest tests/test_hard_filters.py -v
```

Run a single test:
```bash
pytest tests/test_hard_filters.py::test_fails_on_disallowed_location -v
```

Try the job scorer end-to-end (needs `ANTHROPIC_API_KEY` set, makes a real API call):
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

There is no lint/format command configured yet.

## Data files (edit before running anything)

The system's output is only as good as what's filled in here — these are hand-edited,
not generated:

- `data/profile.yaml` — candidate profile
- `data/skills.yaml` — candidate skills
- `data/constraints.yaml` — hard filter rules (allowed locations, employment types,
  experience ceiling, excluded keywords, company cooldown days)
- `data/evidence.yaml` — every factual claim the candidate can make, each with a
  stable `id` (e.g. `EXP001`, `PROJ004`). This ID is the join key used later by the
  claim checker — nothing should ever appear in a generated resume/cover letter that
  isn't traceable back to an evidence ID here.

## Architecture

**Pipeline order matters and is enforced by module boundaries, not just convention:**

1. `app/services/hard_filters.py` — deterministic, non-LLM checks
   (`check_hard_filters`, `check_company_cooldown`) run first. Cheaper and more
   reliable than asking an LLM to check hard constraints like location or excluded
   keywords. Only jobs that pass these should ever reach the scorer.
2. `app/services/job_scorer.py` — `score_job()` loads the three YAML data files,
   fills `JOB_FIT_ANALYSIS_PROMPT`, and calls Claude via `structured_call()` to get
   back a `JobFitAnalysis`. `decide()` then turns that analysis into one of
   `REJECT` / `REVIEW_REQUIRED` / `READY_FOR_REVIEW` — this is intentionally not a
   single fit-score threshold; low confidence or any listed risk forces
   `REVIEW_REQUIRED` regardless of score.
3. (Not yet built) resume/cover-letter generation → claim validation → ATS
   (DOCX→PDF round trip) validation → dashboard. Build in that order; the project
   plan calls for a test-gate on each stage before starting the next.

**LLM access is centralized in `app/llm/`:**
- `anthropic_client.py` — the *only* place that should construct an `Anthropic()`
  client or call the SDK directly. `structured_call(prompt, output_schema)` wraps
  `client.messages.parse(output_format=...)` so callers get back a validated
  Pydantic instance instead of hand-parsed JSON. New LLM call sites should go
  through this wrapper, not around it. It raises on API failure by design —
  callers must catch and log, never silently swallow a failed analysis.
- `schemas.py` — every LLM call's output shape, as Pydantic models
  (`JobFitAnalysis`, `ScreeningAnswer`, `ClaimCheckResult`, `GeneratedResumeSection`,
  etc.). Add new schemas here when adding a new LLM call.
- `prompts.py` — prompt templates as plain `.format()` strings, one constant per
  LLM call (`JOB_FIT_ANALYSIS_PROMPT`, `CLAIM_CHECK_PROMPT`). Prompts explicitly
  instruct the model not to invent skills/experience beyond what's in the evidence
  YAML, and the (planned) claim checker is deliberately strict: an unverified claim
  blocks the application even if it looks plausible.

**Database (`schema.sql`):** run once by hand to bootstrap Postgres; the comment at
the top of the file says to switch to Alembic migrations (`alembic init migrations`)
once past the POC stage rather than continuing to hand-edit this file. Tables:
`jobs`, `job_analysis`, `evidence`, `generated_documents`, `applications`,
`company_application_history` — this mirrors the pipeline stages above (a job is
discovered, analyzed, has documents generated against it, and becomes an
application, with per-company cooldown tracked separately).

## Known repo quirk

There is a stray, empty directory in the repo root literally named
`{app/api,app/services,app/llm,app/sources,app/models,data,tests,documents,generated}`
— the artifact of a `mkdir {a,b,c}` brace-expansion that was run in a shell without
brace expansion support. It is not part of the project structure; don't create files
inside it.
