"""placeinator.placement.candidates -- confidence-scored candidate
identification (spec §7: "Produce a confidence score for ambiguous matches").

Weights are calibrated against spec's own worked example, which has only a
name column -- a strong name-only match must clear the review-queue floor on
its own, not just when corroborated by email/student ID. See the module's
own docstring for the full reasoning; these tests pin the resulting
behavior, not just the arithmetic.
"""

from __future__ import annotations

from placeinator.db.models import Profile
from placeinator.placement.candidates import AUTO_ACCEPT_CONFIDENCE, identify_candidate


def _profile(**overrides) -> Profile:
    defaults = dict(
        full_name="Jane Doe",
        email="jane.doe@college.edu",
        student_id="CS2024001",
        name_aliases=["J. Doe"],
    )
    return Profile(**{**defaults, **overrides})


def test_a_strong_name_only_match_clears_the_review_floor():
    match = identify_candidate({"candidate": "Jane Doe"}, _profile())
    assert match is not None
    assert match.needs_review is True  # a single signal alone never auto-accepts
    assert match.matched_on == ("name",)


def test_a_clearly_different_name_is_not_a_match_at_all():
    assert identify_candidate({"candidate": "John Smith"}, _profile()) is None


def test_exact_email_match_alone_needs_review_not_auto_accept():
    """A single signal, even a strong exact one, doesn't corroborate itself
    -- spec frames this as "ambiguous matches" needing a human look."""
    match = identify_candidate({"email": "jane.doe@college.edu"}, _profile())
    assert match is not None
    assert match.needs_review is True


def test_email_and_name_together_auto_accept():
    match = identify_candidate(
        {"email": "jane.doe@college.edu", "candidate": "Jane Doe"}, _profile()
    )
    assert match is not None
    assert match.confidence >= AUTO_ACCEPT_CONFIDENCE
    assert match.needs_review is False
    assert set(match.matched_on) == {"email", "name"}


def test_a_name_alias_is_checked_too():
    """Profile.name_aliases exists specifically for this (spec §7:
    "Normalized name" as a matching signal, and the alias column's own
    comment in db/models.py)."""
    match = identify_candidate({"candidate": "J. Doe"}, _profile())
    assert match is not None
    assert match.matched_on == ("name",)


def test_student_id_match_alone_needs_review():
    match = identify_candidate({"student_id": "CS2024001"}, _profile())
    assert match is not None
    assert match.needs_review is True


def test_no_recognizable_signal_is_not_a_match():
    assert identify_candidate({}, _profile()) is None
