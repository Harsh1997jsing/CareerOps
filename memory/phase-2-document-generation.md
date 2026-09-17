# Phase 2: Resume + cover letter generator

## What's there

- `app/services/resume_generator.py` — `generate_resume()` produces all 5
  sections (summary, skills, experience, projects, education), one LLM call
  per section, strictly from `data/skills.yaml` + `data/evidence.yaml`.
  Never reads a previously generated resume back in.
- `app/services/cover_letter.py` — `generate_cover_letter()` targets
  250-400 words from `data/evidence.yaml` + `data/profile.yaml`, matched to
  the candidate's tone via `data/voice_samples/`.
- `app/services/docx_writer.py` — shared by both; only `add_heading`/
  `add_paragraph`, so output is always single-column with no tables, text
  boxes, or images.
- New schema: `GeneratedCoverLetter` in `app/llm/schemas.py`.
- New prompts: `RESUME_SECTION_PROMPT`, `COVER_LETTER_PROMPT` in
  `app/llm/prompts.py`.

## Decisions worth knowing

- **Keyword-density guard is a warning, not a hard block.**
  `check_keyword_density()` flags resume sections that mirror 6+
  consecutive words from the job description verbatim. Short overlaps (a
  skill name) are expected and ignored. This isn't a factual-accuracy
  concern — that's what Phase 3's claim validator hard-blocks on — so it
  surfaces `keyword_density_warnings` for a human to look at rather than
  failing generation.
- **Word count is computed in Python from the actual text, never trusted
  from the model's own claimed count** — `cover_letter.py` does
  `len(content.split())` itself.
- **Voice samples require at least 1 file, recommend 3-5.**
  `load_voice_samples()` raises `NoVoiceSamplesError` with an explanatory
  message if `data/voice_samples/` has none — it explicitly skips any file
  named `README` (case-insensitive) so the instructional README placed
  there isn't picked up as a sample.
- `data/voice_samples/` is currently empty except that README — cover
  letter generation will refuse to run for real until samples are added.

## Testing

All tests mock `structured_call` — no API key needed. `check_keyword_density`
and the DOCX structure checks are pure functions tested directly with
fixture text/documents.
