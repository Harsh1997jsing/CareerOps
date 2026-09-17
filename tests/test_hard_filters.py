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
