"""Request/response shapes for onboarding and preferences.

Mirrors placeinator.db.models.Profile / Preferences field-for-field. Kept as
plain Pydantic models rather than reusing the ORM classes directly, so the
wire contract can evolve independently of storage.
"""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field

from placeinator.db.enums import WorkMode


class PreferencesIn(BaseModel):
    target_roles: list[str] = Field(default_factory=list)
    preferred_industries: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    work_mode: WorkMode = WorkMode.ANY

    min_salary: float | None = None
    preferred_salary_min: float | None = None
    preferred_salary_max: float | None = None
    currency: str = "INR"

    willing_to_relocate: bool = True
    target_experience_years: float | None = Field(default=None, ge=0)

    accepts_fixed_term: bool = True
    max_contract_months: int | None = Field(default=None, ge=0)
    accepts_service_bond: bool = True
    max_bond_months: int | None = Field(default=None, ge=0)
    other_restrictions: str | None = None

    # Minimum overall_score (0..1) for a job to surface as a personalized
    # notification (spec §2) -- the Settings page's Notifications control.
    notification_threshold: float = Field(default=0.6, ge=0.0, le=1.0)


class PreferencesOut(PreferencesIn):
    pass


class ProfileIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    phone: str | None = None
    college: str | None = None
    department: str | None = None
    student_id: str | None = None
    name_aliases: list[str] = Field(default_factory=list)
    preferences: PreferencesIn = Field(default_factory=PreferencesIn)


class ProfileOut(BaseModel):
    id: int
    full_name: str
    email: str
    phone: str | None
    college: str | None
    department: str | None
    student_id: str | None
    name_aliases: list[str]
    onboarded: bool
    preferences: PreferencesOut | None

    model_config = {"from_attributes": True}
