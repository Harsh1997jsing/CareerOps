# Phase 0-1: Scaffold (pre-existing)

Built before this memory log started; recorded here for completeness.

## What's there

- `data/*.yaml` — profile, skills, constraints, evidence templates
- `app/services/hard_filters.py` — `check_hard_filters()` (location,
  employment type, years-required ceiling, excluded keywords) and
  `check_company_cooldown()` (blocks re-applying to a company inside a
  cooldown window). Both deterministic, no LLM call.
- `app/llm/anthropic_client.py` — the single wrapper around the Anthropic
  SDK (`structured_call()`), so the model string and retry/error behavior
  live in one place.
- `app/llm/schemas.py` — Pydantic output schemas for every LLM call.
- `app/llm/prompts.py` — prompt templates as `.format()` strings.
- `app/services/job_scorer.py` — `score_job()` calls Claude for a
  `JobFitAnalysis`; `decide()` maps it to `REJECT` / `REVIEW_REQUIRED` /
  `READY_FOR_REVIEW` (never a single fit-score cutoff — low confidence or
  any risk forces `REVIEW_REQUIRED`).
- `schema.sql` — full Postgres schema: `jobs`, `job_analysis`, `evidence`,
  `generated_documents`, `applications`, `company_application_history`.
- `tests/test_hard_filters.py` — passing, no API key needed.

## Known issue carried forward

`JobFitAnalysis.missing_requirements` (the Pydantic field name) and
`job_analysis.missing_skills` (the DB column name) name the same concept
differently. Nothing writes a `JobFitAnalysis` into `job_analysis` yet, so
it's latent — see [known-gaps.md](known-gaps.md).
