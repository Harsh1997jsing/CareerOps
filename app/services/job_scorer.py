"""
Only jobs that pass hard_filters.py reach this module.
"""

import yaml
from app.llm.anthropic_client import structured_call
from app.llm.schemas import JobFitAnalysis
from app.llm.prompts import JOB_FIT_ANALYSIS_PROMPT


def score_job(job_description: str, skills_path: str, evidence_path: str, constraints_path: str) -> JobFitAnalysis:
    with open(skills_path) as f:
        skills_yaml = f.read()
    with open(evidence_path) as f:
        evidence_yaml = f.read()
    with open(constraints_path) as f:
        constraints_yaml = f.read()

    prompt = JOB_FIT_ANALYSIS_PROMPT.format(
        job_description=job_description,
        skills_yaml=skills_yaml,
        evidence_yaml=evidence_yaml,
        constraints_yaml=constraints_yaml,
    )

    result = structured_call(prompt, JobFitAnalysis)
    return result  # type: ignore[return-value]


def decide(analysis: JobFitAnalysis) -> str:
    """
    Replaces a single fixed threshold with a fit + confidence + risk decision.
    """
    if not analysis.eligible:
        return "REJECT"
    if analysis.confidence == "low" or len(analysis.risks) > 0:
        return "REVIEW_REQUIRED"
    if analysis.fit_score >= 75 and analysis.confidence in ("high", "medium"):
        return "READY_FOR_REVIEW"
    return "REVIEW_REQUIRED"
