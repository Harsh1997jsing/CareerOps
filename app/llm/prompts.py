"""Prompt templates for Claude LLM calls across the CareerOps pipeline.

Contains prompt templates for:
- `JOB_FIT_ANALYSIS_PROMPT`: Evaluates job postings against candidate skills,
  evidence, and constraints.
- `RESUME_SECTION_PROMPT`: Drafts targeted resume sections grounded in candidate
  evidence entries without inventing claims or echoing job descriptions verbatim.
- `COVER_LETTER_PROMPT`: Generates cover letters reflecting candidate voice samples
  and evidence.
- `CLAIM_CHECK_PROMPT`: Fact-checks generated documents strictly against candidate
  evidence IDs to block unsupported claims.
"""

JOB_FIT_ANALYSIS_PROMPT = """You are analyzing whether a candidate is a good fit for a job.
Only use information given below. Never invent skills, experience, or metrics
that are not present in the candidate's evidence.

JOB DESCRIPTION:
{job_description}

CANDIDATE SKILLS:
{skills_yaml}

CANDIDATE EXPERIENCE / EVIDENCE:
{evidence_yaml}

CANDIDATE CONSTRAINTS:
{constraints_yaml}

Analyze the fit. Be honest about gaps — do not inflate the fit score to be
encouraging. A missing required skill should lower the score and confidence,
and be listed in missing_requirements.
"""

RESUME_SECTION_PROMPT = """You are writing the "{section}" section of a resume.
Use ONLY information present in CANDIDATE EVIDENCE below. Never invent
skills, experience, metrics, companies, dates, or achievements that are not
directly supported by an evidence entry. Every fact you use must come from
an evidence entry — record its id in evidence_ids_used.

Write for a human reader first. Do not copy the job description's exact
wording — describe the candidate's own experience in the candidate's own
terms, even where the underlying skill overlaps with what the job asks for.

JOB DESCRIPTION:
{job_description}

CANDIDATE SKILLS:
{skills_yaml}

CANDIDATE EVIDENCE:
{evidence_yaml}

Write only the "{section}" section content. If the evidence does not support
a strong "{section}" section for this job, write a shorter, honest one rather
than padding it with unsupported claims.
"""

COVER_LETTER_PROMPT = """You are writing a cover letter for this candidate, as
the candidate, in their own voice. Use ONLY information present in CANDIDATE
EVIDENCE below — never invent skills, experience, metrics, or achievements
that are not directly supported by an evidence entry. Record the evidence
ids you used in evidence_ids_used.

Reference the job's actual requirements and specific pieces of candidate
evidence — avoid generic, could-apply-to-any-job filler. Target a length of
{min_words}-{max_words} words.

Match the tone, sentence rhythm, and vocabulary of the VOICE SAMPLES below —
these are the candidate's own past writing. Do not copy their content or
subject matter, only the way they write.

JOB DESCRIPTION:
{job_description}

CANDIDATE PROFILE:
{profile_yaml}

CANDIDATE EVIDENCE:
{evidence_yaml}

VOICE SAMPLES (style reference only):
{voice_samples}
"""

CLAIM_CHECK_PROMPT = """You are a fact-checker. Compare each claim in the
GENERATED TEXT below against the EVIDENCE list. For every factual claim
(company names, titles, dates, technologies, metrics, achievements),
determine whether it is directly supported by an evidence ID.

If a claim has no matching evidence_id, mark it unverified and list it
in blocking_claims. Do not be lenient — an unverified claim should block
the application, even if it seems plausible.

GENERATED TEXT:
{generated_text}

EVIDENCE:
{evidence_yaml}
"""
