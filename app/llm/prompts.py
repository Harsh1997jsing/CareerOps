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
