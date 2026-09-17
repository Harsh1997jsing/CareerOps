"""
Deterministic filters applied before a job ever reaches Claude.
Cheaper and more reliable than asking an LLM to check hard constraints.
"""

from dataclasses import dataclass


@dataclass
class FilterResult:
    passed: bool
    reasons: list[str]


def check_hard_filters(job: dict, constraints: dict) -> FilterResult:
    """
    job: dict with keys location, employment_type, years_required, description
    constraints: parsed contents of data/constraints.yaml
    """
    reasons = []

    if job.get("location") not in constraints["allowed_locations"]:
        reasons.append(f"location '{job.get('location')}' not in allowed_locations")

    if job.get("employment_type") not in constraints["employment_types"]:
        reasons.append(f"employment_type '{job.get('employment_type')}' not allowed")

    years_required = job.get("years_required")
    if years_required is not None:
        max_allowed = constraints["minimum_experience_years"] + constraints["acceptable_experience_gap_years"]
        if years_required > max_allowed:
            reasons.append(f"requires {years_required} years, candidate ceiling is {max_allowed}")

    description = (job.get("description") or "").lower()
    for keyword in constraints.get("exclude_keywords", []):
        if keyword.lower() in description:
            reasons.append(f"excluded keyword found: '{keyword}'")

    return FilterResult(passed=len(reasons) == 0, reasons=reasons)


def check_company_cooldown(company: str, applied_dates: list, cooldown_days: int) -> FilterResult:
    """
    applied_dates: list of datetime objects for prior applications to this company.
    Prevents re-applying to the same company inside the cooldown window —
    a common signal that gets applications auto-rejected as spammy.
    """
    from datetime import datetime, timedelta

    if not applied_dates:
        return FilterResult(passed=True, reasons=[])

    most_recent = max(applied_dates)
    cutoff = datetime.now() - timedelta(days=cooldown_days)

    if most_recent > cutoff:
        days_left = (most_recent - cutoff).days
        return FilterResult(
            passed=False,
            reasons=[f"applied to {company} {(datetime.now() - most_recent).days} days ago; "
                     f"{days_left} days left in cooldown"]
        )
    return FilterResult(passed=True, reasons=[])
