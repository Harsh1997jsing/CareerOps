"""
Only jobs that pass hard_filters.py reach this module (enforced by
app/services/jobs.py's hard_filter_job(), called from
POST /jobs/{job_id}/analyze before this module's score_job()).
"""

from app.llm.anthropic_client import structured_call
from app.llm.prompts import JOB_FIT_ANALYSIS_PROMPT
from app.llm.schemas import JobFitAnalysis

# decide()'s possible outcomes, also used directly by
# app/api/routes/jobs.py's analyze_job() when a job fails hard_filter_job()
# and never reaches decide() at all (same terminal status either way: an
# LLM-ineligible verdict and a deterministic-constraint failure both mean
# "don't pursue this job").
REJECT_STATUS = "REJECT"
REVIEW_REQUIRED_STATUS = "REVIEW_REQUIRED"
READY_FOR_REVIEW_STATUS = "READY_FOR_REVIEW"


def score_job(job_description: str, skills_path: str, evidence_path: str, constraints_path: str) -> JobFitAnalysis:
    """Evaluate candidate fit for a job using Claude and structured schema output.

    Loads candidate skills, evidence, and constraints, populating the job fit prompt.
    Returns honest assessment of matches, missing requirements, risks, and fit score.

    Args:
        job_description: Full text description of the job posting.
        skills_path: Path to candidate skills YAML file.
        evidence_path: Path to candidate evidence YAML file.
        constraints_path: Path to candidate constraints YAML file.

    Returns:
        JobFitAnalysis: Structured analysis with score, confidence, matches, and gaps.

    Raises:
        OSError: If any of the YAML files cannot be read.
    """
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
    """Determine the next application workflow status based on LLM fit analysis.

    Replaces a single fixed threshold with a fit + confidence + risk decision:
    - 'REJECT': Candidate is ineligible.
    - 'READY_FOR_REVIEW': Fit score >= 75 with high/medium confidence and zero risks.
    - 'REVIEW_REQUIRED': Low confidence, any risks present, or moderate fit scores.

    Args:
        analysis: JobFitAnalysis instance containing scoring metrics and risks.

    Returns:
        str: Status string ('REJECT', 'READY_FOR_REVIEW', or 'REVIEW_REQUIRED').
    """
    if not analysis.eligible:
        return REJECT_STATUS
    if analysis.confidence == "low" or len(analysis.risks) > 0:
        return REVIEW_REQUIRED_STATUS
    if analysis.fit_score >= 75 and analysis.confidence in ("high", "medium"):
        return READY_FOR_REVIEW_STATUS
    return REVIEW_REQUIRED_STATUS
