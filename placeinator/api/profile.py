"""Profile and onboarding endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from placeinator.db.models import Profile
from placeinator.db.session import get_session
from placeinator.profile.schemas import PreferencesOut, ProfileIn, ProfileOut
from placeinator.profile.service import get_profile, upsert_profile

router = APIRouter(prefix="/api/profile", tags=["profile"])


def _to_out(profile: Profile) -> ProfileOut:
    preferences = (
        PreferencesOut.model_validate(profile.preferences, from_attributes=True)
        if profile.preferences is not None
        else None
    )
    return ProfileOut(
        id=profile.id,
        full_name=profile.full_name,
        email=profile.email,
        phone=profile.phone,
        college=profile.college,
        department=profile.department,
        student_id=profile.student_id,
        name_aliases=profile.name_aliases,
        onboarded=profile.onboarded_at is not None,
        preferences=preferences,
    )


@router.get("", response_model=ProfileOut)
def read_profile(session: Session = Depends(get_session)) -> ProfileOut:
    profile = get_profile(session)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "profile not onboarded yet")
    return _to_out(profile)


@router.put("", response_model=ProfileOut)
def write_profile(data: ProfileIn, session: Session = Depends(get_session)) -> ProfileOut:
    """Upsert semantics: onboards on the first call, edits on every call after
    (spec §1 requires profile information to remain editable)."""
    profile = upsert_profile(session, data)
    return _to_out(profile)
