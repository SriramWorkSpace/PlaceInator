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
from placeinator.placement.candidates import (
    AUTO_ACCEPT_CONFIDENCE,
    identify_candidate,
    mentions_candidate_in_text,
)


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


def test_mentions_candidate_in_text_finds_a_clean_name():
    text = "Placement Shortlist\nJane Doe - jane.doe@college.edu - SHORTLISTED"
    assert mentions_candidate_in_text(text, _profile()) is True


def test_mentions_candidate_in_text_tolerates_real_ocr_noise():
    """Pinned against actual RapidOCR output observed on a synthetic scanned
    PDF during development (a stray space in the email, a period instead of
    a colon) -- the name's fuzzy match is what carries this, not the email's
    exact-substring check, which the same noise breaks."""
    text = "PlacementShortlist\nJane Doe-jane @college.edu-SHORTLISTED\nCompany.Acme Corp"
    assert mentions_candidate_in_text(text, _profile()) is True


def test_mentions_candidate_in_text_rejects_an_unrelated_document():
    text = "Placement Shortlist\nJohn Smith - john.smith@college.edu - SHORTLISTED"
    assert mentions_candidate_in_text(text, _profile()) is False


def test_mentions_candidate_in_text_matches_on_email_alone():
    text = "contact jane.doe@college.edu for details, ref XJ991"
    assert mentions_candidate_in_text(text, _profile()) is True


def test_mentions_candidate_in_text_matches_on_student_id_alone():
    text = "roll number CS2024001 has been shortlisted"
    assert mentions_candidate_in_text(text, _profile()) is True


def test_mentions_candidate_in_text_matches_a_name_alias():
    text = "J. Doe has been shortlisted for the next round"
    assert mentions_candidate_in_text(text, _profile()) is True
