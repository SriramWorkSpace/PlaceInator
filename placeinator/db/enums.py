"""Canonical vocabularies shared across modules.

These mirror the normalized states in feature_architecture.md; keeping them in
one place stops the parsing, scoring, and UI layers from drifting apart.
"""

from __future__ import annotations

from enum import StrEnum


class WorkMode(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    ANY = "any"


class JobType(StrEnum):
    FULL_TIME = "full_time"
    INTERNSHIP = "internship"
    CONTRACT = "contract"
    PART_TIME = "part_time"
    UNKNOWN = "unknown"


class ChunkKind(StrEnum):
    """Typed spans extracted from a resume."""

    SKILL = "skill"
    PROJECT_BULLET = "project_bullet"
    EXPERIENCE_BULLET = "experience_bullet"
    EDUCATION = "education"
    CERTIFICATION = "certification"
    ACHIEVEMENT = "achievement"
    SUMMARY = "summary"


class RequirementKind(StrEnum):
    """Typed lines extracted from a job description."""

    REQUIRED_SKILL = "required_skill"
    PREFERRED_SKILL = "preferred_skill"
    RESPONSIBILITY = "responsibility"
    QUALIFICATION = "qualification"
    ROLE_TITLE = "role_title"


class PlacementStatus(StrEnum):
    """Normalized from arbitrary placement-sheet wording."""

    SHORTLISTED = "shortlisted"
    REJECTED = "rejected"
    PENDING = "pending"
    UNKNOWN = "unknown"


class EventType(StrEnum):
    INTERVIEW = "interview"
    TECHNICAL_ROUND = "technical_round"
    HR_ROUND = "hr_round"
    CODING_TEST = "coding_test"
    ASSESSMENT = "assessment"
    PRE_PLACEMENT_TALK = "pre_placement_talk"
    OTHER = "other"


class SourceKind(StrEnum):
    MANUAL = "manual"
    INDEED = "indeed"
    LINKEDIN = "linkedin"
    NAUKRI = "naukri"
    ATS_FEED = "ats_feed"
