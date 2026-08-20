"""Applies the user's preferences to one job: hard constraints that eliminate
it outright, and soft preferences that only ever influence ranking.

Deliberately separate from placeinator.matching.scoring, which only ever
knows about resume/JD content and never about user preferences (see that
module's MatchExplanation.personalized_score docstring). This module is the
mirror image -- it only ever knows about a job and Preferences, never resume
content. placeinator.jobs.service composes both into the final ranking.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from placeinator.db.enums import WorkMode
from placeinator.db.models import Job, Preferences

# Weight of the soft-preference signal in the combined job ranking, mirroring
# placeinator.matching.scoring.COMPONENT_WEIGHTS's role -- centralized here
# rather than inlined so it moves to config/scoring.toml alongside the other
# weights in the same later milestone.
SOFT_PREFERENCE_WEIGHT = 0.3
SEMANTIC_MATCH_WEIGHT = 1.0 - SOFT_PREFERENCE_WEIGHT


@dataclass(frozen=True)
class SoftPreferenceScore:
    value: float  # 0..1
    reasons: list[str] = field(default_factory=list)


def apply_hard_filters(job: Job, preferences: Preferences | None) -> str | None:
    """Returns the reason a job is eliminated, or None if it survives.

    Absence of data is never treated as a violation -- a job missing a salary
    range, bond duration, or experience range simply isn't checked against
    that constraint, since silence isn't evidence of unsuitability. Only an
    explicit, comparable mismatch eliminates a job (spec §2's Hard
    Constraints: minimum salary, maximum bond duration, required experience
    range, unacceptable location).
    """
    if preferences is None:
        return None

    if (
        preferences.min_salary is not None
        and job.salary_max is not None
        and job.salary_max < preferences.min_salary
    ):
        return (
            f"Salary up to {job.salary_max:.0f} {job.currency or ''} is below "
            f"your minimum of {preferences.min_salary:.0f}"
        ).strip()

    if not preferences.accepts_service_bond and job.bond_months:
        return "Requires a service bond, which you've opted out of"

    if (
        preferences.accepts_service_bond
        and preferences.max_bond_months is not None
        and job.bond_months is not None
        and job.bond_months > preferences.max_bond_months
    ):
        return (
            f"Bond of {job.bond_months} months exceeds your maximum of "
            f"{preferences.max_bond_months}"
        )

    if not preferences.accepts_fixed_term and job.contract_months:
        return "Fixed-term contract, which you've opted out of"

    if (
        preferences.accepts_fixed_term
        and preferences.max_contract_months is not None
        and job.contract_months is not None
        and job.contract_months > preferences.max_contract_months
    ):
        return (
            f"Contract of {job.contract_months} months exceeds your maximum of "
            f"{preferences.max_contract_months}"
        )

    if preferences.target_experience_years is not None:
        years = preferences.target_experience_years
        if job.experience_min_years is not None and years < job.experience_min_years:
            return f"Requires {job.experience_min_years:.0f}+ years of experience"
        if job.experience_max_years is not None and years > job.experience_max_years:
            return f"Capped at {job.experience_max_years:.0f} years of experience, above yours"

    if (
        not preferences.willing_to_relocate
        and job.work_mode != WorkMode.REMOTE
        and job.location
        and preferences.preferred_locations
        and not any(loc.lower() in job.location.lower() for loc in preferences.preferred_locations)
    ):
        return (
            f"{job.location} is outside your preferred locations and you're not "
            "open to relocating"
        )

    return None


def score_soft_preferences(job: Job, preferences: Preferences | None) -> SoftPreferenceScore:
    """0..1 score for preferences that influence ranking but never eliminate a
    job (spec §2's Soft Preferences: preferred city, work mode, industry).
    A preference the user never set contributes no signal either way, rather
    than counting as a miss."""
    if preferences is None:
        return SoftPreferenceScore(value=0.5)

    signals: list[float] = []
    reasons: list[str] = []

    if preferences.work_mode != WorkMode.ANY:
        if job.work_mode == preferences.work_mode:
            signals.append(1.0)
            reasons.append(f"Matches your preferred work mode ({job.work_mode.value})")
        else:
            signals.append(0.0)

    if preferences.preferred_locations and job.location:
        if any(loc.lower() in job.location.lower() for loc in preferences.preferred_locations):
            signals.append(1.0)
            reasons.append(f"Located in {job.location}, one of your preferred cities")
        else:
            signals.append(0.0)

    if preferences.target_roles and job.designation:
        if any(role.lower() in job.designation.lower() for role in preferences.target_roles):
            signals.append(1.0)
            reasons.append(f"Matches your target role ({job.designation})")
        else:
            signals.append(0.3)

    if preferences.preferred_salary_min is not None and job.salary_max is not None:
        signals.append(1.0 if job.salary_max >= preferences.preferred_salary_min else 0.5)

    if not signals:
        return SoftPreferenceScore(value=0.5)

    return SoftPreferenceScore(value=sum(signals) / len(signals), reasons=reasons)
