"""placeinator.jobs.filtering -- hard constraints (spec §2) that eliminate a
job, and soft preferences that only ever influence ranking.

Job and Preferences instances here are plain in-memory ORM objects, never
persisted -- apply_hard_filters/score_soft_preferences only ever read
attributes, so no session or database is needed to exercise them.
"""

from __future__ import annotations

from placeinator.db.enums import WorkMode
from placeinator.db.models import Job, Preferences
from placeinator.jobs.filtering import apply_hard_filters, score_soft_preferences


def _job(**overrides) -> Job:
    defaults = dict(company="Acme", designation="Backend Engineer", description="...")
    return Job(**{**defaults, **overrides})


def _preferences(**overrides) -> Preferences:
    # mapped_column(default=...) only applies at INSERT/flush time, not at
    # bare construction -- these tests never flush, so every field the real
    # PreferencesIn/_upsert_preferences path would always populate explicitly
    # must be set here too, or a bool silently reads back as None instead of
    # its real default and the test stops exercising the intended behavior.
    defaults = dict(
        target_roles=[],
        preferred_industries=[],
        preferred_locations=[],
        work_mode=WorkMode.ANY,
        willing_to_relocate=True,
        accepts_fixed_term=True,
        accepts_service_bond=True,
    )
    return Preferences(**{**defaults, **overrides})


def test_no_preferences_never_filters():
    assert apply_hard_filters(_job(salary_max=10), None) is None


def test_salary_below_minimum_is_filtered():
    job = _job(salary_max=500000, currency="INR")
    prefs = _preferences(min_salary=800000)
    reason = apply_hard_filters(job, prefs)
    assert reason is not None
    assert "500000" in reason or "500,000" in reason


def test_missing_salary_is_not_checked():
    job = _job(salary_max=None)
    prefs = _preferences(min_salary=800000)
    assert apply_hard_filters(job, prefs) is None


def test_service_bond_opt_out_filters_any_bonded_job():
    job = _job(bond_months=12)
    prefs = _preferences(accepts_service_bond=False)
    assert apply_hard_filters(job, prefs) is not None


def test_bond_within_accepted_maximum_passes():
    job = _job(bond_months=6)
    prefs = _preferences(accepts_service_bond=True, max_bond_months=12)
    assert apply_hard_filters(job, prefs) is None


def test_bond_exceeding_maximum_is_filtered():
    job = _job(bond_months=24)
    prefs = _preferences(accepts_service_bond=True, max_bond_months=12)
    assert apply_hard_filters(job, prefs) is not None


def test_experience_requirement_above_users_years_is_filtered():
    job = _job(experience_min_years=5)
    prefs = _preferences(target_experience_years=1)
    assert apply_hard_filters(job, prefs) is not None


def test_experience_within_range_passes():
    job = _job(experience_min_years=1, experience_max_years=4)
    prefs = _preferences(target_experience_years=2)
    assert apply_hard_filters(job, prefs) is None


def test_unwilling_to_relocate_and_outside_preferred_locations_is_filtered():
    job = _job(location="Berlin", work_mode=WorkMode.ONSITE)
    prefs = _preferences(willing_to_relocate=False, preferred_locations=["Bengaluru"])
    assert apply_hard_filters(job, prefs) is not None


def test_remote_job_survives_relocation_constraint():
    job = _job(location="Berlin", work_mode=WorkMode.REMOTE)
    prefs = _preferences(willing_to_relocate=False, preferred_locations=["Bengaluru"])
    assert apply_hard_filters(job, prefs) is None


def test_soft_preferences_default_to_neutral_with_no_preferences():
    score = score_soft_preferences(_job(), None)
    assert score.value == 0.5
    assert score.reasons == []


def test_soft_preferences_reward_matching_work_mode():
    job = _job(work_mode=WorkMode.REMOTE)
    prefs = _preferences(work_mode=WorkMode.REMOTE)
    score = score_soft_preferences(job, prefs)
    assert score.value == 1.0
    assert score.reasons


def test_soft_preferences_penalize_mismatched_work_mode():
    job = _job(work_mode=WorkMode.ONSITE)
    prefs = _preferences(work_mode=WorkMode.REMOTE)
    score = score_soft_preferences(job, prefs)
    assert score.value == 0.0
