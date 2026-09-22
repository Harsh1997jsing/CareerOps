from app.services.hard_filters import check_hard_filters, check_company_cooldown
from datetime import datetime, timedelta

CONSTRAINTS = {
    "allowed_locations": ["Remote", "Bangalore"],
    "employment_types": ["Full-time"],
    "minimum_experience_years": 0,
    "acceptable_experience_gap_years": 1,
    "exclude_keywords": ["unpaid internship"],
    "company_cooldown_days": 30,
}


def test_passes_when_all_constraints_met():
    job = {"location": "Bangalore", "employment_type": "Full-time",
           "years_required": 1, "description": "Great Python role"}
    result = check_hard_filters(job, CONSTRAINTS)
    assert result.passed


def test_fails_on_disallowed_location():
    job = {"location": "Mumbai", "employment_type": "Full-time",
           "years_required": 0, "description": ""}
    result = check_hard_filters(job, CONSTRAINTS)
    assert not result.passed
    assert any("location" in r for r in result.reasons)


def test_fails_on_excluded_keyword():
    job = {"location": "Remote", "employment_type": "Full-time",
           "years_required": 0, "description": "This is an unpaid internship"}
    result = check_hard_filters(job, CONSTRAINTS)
    assert not result.passed


def test_company_cooldown_blocks_recent_application():
    applied = [datetime.now() - timedelta(days=5)]
    result = check_company_cooldown("Acme", applied, cooldown_days=30)
    assert not result.passed


def test_company_cooldown_allows_after_window():
    applied = [datetime.now() - timedelta(days=45)]
    result = check_company_cooldown("Acme", applied, cooldown_days=30)
    assert result.passed


def test_fails_closed_when_constraints_yaml_is_missing_keys():
    # A KeyError here would crash the whole /jobs/{id}/analyze request
    # (see app/services/jobs.py:hard_filter_job) instead of just failing
    # this one job — missing config should block, not crash or silently
    # admit an unverifiable job.
    job = {"location": "Bangalore", "employment_type": "Full-time", "description": ""}
    result = check_hard_filters(job, {})
    assert not result.passed
    assert any("location" in r for r in result.reasons)
    assert any("employment_type" in r for r in result.reasons)


def test_years_required_check_is_skipped_without_a_ceiling_when_not_provided():
    # years_required is only ever checked when the job itself provides it —
    # confirms the fail-closed default (0 + 0 = 0 ceiling) doesn't get
    # exercised at all for the common case (no source populates years_required).
    job = {"location": "Bangalore", "employment_type": "Full-time", "description": ""}
    result = check_hard_filters(job, {"allowed_locations": ["Bangalore"], "employment_types": ["Full-time"]})
    assert result.passed
