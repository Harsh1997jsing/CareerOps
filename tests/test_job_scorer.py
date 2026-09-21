from app.llm.schemas import JobFitAnalysis
from app.services.job_scorer import (
    READY_FOR_REVIEW_STATUS,
    REJECT_STATUS,
    REVIEW_REQUIRED_STATUS,
    decide,
)


def _analysis(**overrides):
    defaults = dict(
        eligible=True, fit_score=80, confidence="high",
        strong_matches=[], missing_requirements=[], risks=[], summary="",
    )
    return JobFitAnalysis(**{**defaults, **overrides})


def test_decide_rejects_ineligible_candidate():
    assert decide(_analysis(eligible=False)) == REJECT_STATUS


def test_decide_requires_review_on_low_confidence():
    assert decide(_analysis(confidence="low")) == REVIEW_REQUIRED_STATUS


def test_decide_requires_review_when_risks_present():
    assert decide(_analysis(risks=["visa sponsorship unclear"])) == REVIEW_REQUIRED_STATUS


def test_decide_ready_for_review_above_threshold_with_no_risks():
    assert decide(_analysis(fit_score=75, confidence="medium")) == READY_FOR_REVIEW_STATUS
    assert decide(_analysis(fit_score=90, confidence="high")) == READY_FOR_REVIEW_STATUS


def test_decide_requires_review_below_threshold_even_with_high_confidence():
    assert decide(_analysis(fit_score=74, confidence="high")) == REVIEW_REQUIRED_STATUS
