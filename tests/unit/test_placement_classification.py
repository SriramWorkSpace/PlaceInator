"""placeinator.placement.classification -- keyword-rule email relevance and
status classification (ADR 0002: no LLM anywhere in this path).
"""

from __future__ import annotations

from placeinator.db.enums import PlacementStatus
from placeinator.placement.classification import classify_status, is_placement_related


def test_a_shortlist_email_is_recognized_as_placement_related():
    assert is_placement_related("You've been shortlisted!", "") is True


def test_an_unrelated_email_is_not():
    assert is_placement_related("Your weekly newsletter", "Here's what's new this week.") is False


def test_spec_wording_maps_to_shortlisted():
    """spec §7's own "Placement Status Classification" examples, verbatim."""
    for phrase in (
        "Shortlisted",
        "Selected for interview",
        "Eligible for technical round",
        "Called for interview",
    ):
        assert classify_status(phrase) == PlacementStatus.SHORTLISTED, phrase


def test_spec_wording_maps_to_rejected():
    for phrase in ("Rejected", "Not selected", "Not shortlisted"):
        assert classify_status(phrase) == PlacementStatus.REJECTED, phrase


def test_spec_wording_maps_to_pending():
    for phrase in ("Under review", "Waitlisted", "Result pending"):
        assert classify_status(phrase) == PlacementStatus.PENDING, phrase


def test_wording_that_matches_nothing_is_unknown_not_a_guess():
    assert classify_status("Please find the attached document.") == PlacementStatus.UNKNOWN


def test_status_is_case_insensitive():
    assert classify_status("SHORTLISTED for the next round") == PlacementStatus.SHORTLISTED
