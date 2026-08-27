"""Profile and preferences persistence.

Single-user application (see placeinator.db.__init__): there is exactly one
Profile row, ever. Every operation here is an upsert against that one row
rather than a create -- there is no "create a second profile" path to guard
against because the schema has no way to disambiguate which one is "current".
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from placeinator.db.models import Job, PlacementRecord, Preferences, Profile
from placeinator.jobs.service import refilter_jobs
from placeinator.placement import auth as gmail_auth
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
    profile.neo_id = data.neo_id
    profile.name_aliases = data.name_aliases

    if is_first_time:
        profile.onboarded_at = datetime.now(UTC)

    preferences = _upsert_preferences(session, profile, data.preferences)
    refilter_jobs(session, preferences)

    session.flush()
    return profile


def reset_all_data(session: Session) -> None:
    """Full local reset -- wipes the profile and everything else in this
    single-user app, back to a genuinely first-run state (spec/ADR: exactly
    one Profile row, ever; this is what makes "delete account" mean "start
    over" rather than needing per-table user-scoping this schema doesn't
    have).

    SQLite's own ON DELETE CASCADE (PRAGMA foreign_keys=ON, see
    placeinator.db.session) does the real work once the two anchors are
    gone: deleting Profile cascades Preferences/Resume, and Resume itself
    cascades ResumeChunk/MatchResult/TailoredResume/OutreachDraft; deleting
    Job cascades JobRequirement and the same MatchResult/TailoredResume/
    OutreachDraft rows from the other side. PlacementRecord is the one table
    with no such anchor -- identified by gmail_message_id, not owned by
    Profile or Job -- so it's deleted explicitly; PlacementEvent cascades
    from that via its own ORM relationship (cascade="all, delete-orphan").

    Also disconnects Gmail: leaving a stale OS-keychain credential behind
    after "deleting the account" would mean the next fresh onboarding starts
    already connected to a Google account nobody asked to connect here.
    """
    session.execute(delete(Job))
    session.execute(delete(PlacementRecord))
    session.execute(delete(Profile))
    session.flush()
    gmail_auth.disconnect()


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
    prefs.notification_threshold = data.notification_threshold
    return prefs
