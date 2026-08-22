"""placeinator.placement.headers -- header-synonym dictionary + rapidfuzz
fallback (ADR 0002's placement-extraction commitment). No LLM, no session
needed -- these are pure string functions.
"""

from __future__ import annotations

from placeinator.placement.headers import classify_header, normalize_row


def test_spec_example_headers_map_to_their_documented_canonical_field():
    """spec §7's own "Document Structure Detection" example, verbatim."""
    assert classify_header("Candidate Name") == "candidate"
    assert classify_header("Student Name") == "candidate"
    assert classify_header("Applicant") == "candidate"
    assert classify_header("Result") == "status"
    assert classify_header("Status") == "status"
    assert classify_header("Selection Status") == "status"
    assert classify_header("Interview Date") == "event_date"
    assert classify_header("Date") == "event_date"
    assert classify_header("Schedule") == "event_date"


def test_case_and_whitespace_are_normalized_before_lookup():
    assert classify_header("  CANDIDATE   NAME  ") == "candidate"


def test_a_close_typo_is_still_recognized_via_rapidfuzz():
    assert classify_header("Studnt Name") == "candidate"


def test_an_unrelated_header_is_left_unrecognized():
    """Below the fuzzy-match threshold -- must not be guessed into some
    canonical field just because it's the "closest" available option."""
    assert classify_header("Remarks by Faculty") is None


def test_normalize_row_drops_unrecognized_columns_rather_than_misattribute():
    row = {
        "Student Name": "Jane Doe",
        "Result": "Selected for interview",
        "Interview Date": "2026-08-25",
        "Unrelated Column": "xyz",
    }
    assert normalize_row(row) == {
        "candidate": "Jane Doe",
        "status": "Selected for interview",
        "event_date": "2026-08-25",
    }


def test_normalize_row_drops_empty_values():
    assert normalize_row({"Candidate Name": ""}) == {}
