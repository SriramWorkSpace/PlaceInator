"""Profile and preferences persistence.

Single-user application (see placeinator.db.__init__): there is exactly one
Profile row, ever. Every operation here is an upsert against that one row
rather than a create -- there is no "create a second profile" path to guard
against because the schema has no way to disambiguate which one is "current".
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from placeinator.db.models import Preferences, Profile
from placeinator.profile.schemas import PreferencesIn, ProfileIn


def get_profile(session: Session) -> Profile | None:
    return session.execute(select(Profile).limit(1)).scalar_one_or_none()


def upsert_profile(session: Session, data: ProfileIn) -> Profile:
    """Create the profile on first onboarding, or update it on every
    subsequent edit (spec §1, "All profile information ... can be edited
    later"). ``onboarded_at`` is set only once, on the first call.
    """
    profile = get_profile(session)
    is_first_time = profile is None
    if profile is None:
        profile = Profile(full_name=data.full_name, email=data.email)
        session.add(profile)

    profile.full_name = data.full_name
    profile.email = data.email
    profile.phone = data.phone
    profile.college = data.college
    profile.department = data.department
    profile.student_id = data.student_id
    profile.name_aliases = data.name_aliases

    if is_first_time:
        profile.onboarded_at = datetime.now(UTC)

    _upsert_preferences(session, profile, data.preferences)

    session.flush()
    return profile


def _upsert_preferences(session: Session, profile: Profile, data: PreferencesIn) -> Preferences:
    prefs = profile.preferences
    if prefs is None:
        prefs = Preferences(profile=profile)
        session.add(prefs)

    prefs.target_roles = data.target_roles
    prefs.preferred_industries = data.preferred_industries
    prefs.preferred_locations = data.preferred_locations
    prefs.work_mode = data.work_mode
    prefs.min_salary = data.min_salary
    prefs.preferred_salary_min = data.preferred_salary_min
    prefs.preferred_salary_max = data.preferred_salary_max
    prefs.currency = data.currency
    prefs.willing_to_relocate = data.willing_to_relocate
    prefs.target_experience_years = data.target_experience_years
    prefs.accepts_fixed_term = data.accepts_fixed_term
    prefs.max_contract_months = data.max_contract_months
    prefs.accepts_service_bond = data.accepts_service_bond
    prefs.max_bond_months = data.max_bond_months
    prefs.other_restrictions = data.other_restrictions
    return prefs
