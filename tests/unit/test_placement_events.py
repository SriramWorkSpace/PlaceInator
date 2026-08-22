"""placeinator.placement.events -- event extraction and the duplicate-
detection key. Uses the real `dateparser` (no model, fast) -- date/time
parsing is exactly the part worth testing against the real library rather
than a stub.
"""

from __future__ import annotations

from datetime import date

from placeinator.db.enums import EventType
from placeinator.placement.events import classify_event_type, compute_dedupe_key, extract_event


def test_spec_example_event_is_extracted_correctly():
    """spec §7's own Google Calendar Integration example: "Technical
    Interview / XYZ Technologies / August 22 / 10:30 AM / Block A"."""
    row = {
        "company": "XYZ Technologies",
        "round": "Technical Interview",
        "event_date": "August 22, 2026",
        "start_time": "10:30 AM",
        "venue": "Block A",
    }
    event = extract_event(row)
    assert event is not None
    assert event.company == "XYZ Technologies"
    assert event.event_type == EventType.TECHNICAL_ROUND
    assert event.event_date == date(2026, 8, 22)
    assert event.start_time == "10:30"
    assert event.venue == "Block A"


def test_a_row_with_neither_company_nor_event_wording_is_not_an_event():
    """A row can be a valid candidate-status update without describing an
    event at all -- e.g. a bare "Result: Rejected" row."""
    assert extract_event({"status": "Rejected"}) is None


def test_classify_event_type_covers_specs_possible_events_list():
    assert classify_event_type("Coding Test") == EventType.CODING_TEST
    assert classify_event_type("Assessment Round") == EventType.ASSESSMENT
    assert classify_event_type("Technical Round 1") == EventType.TECHNICAL_ROUND
    assert classify_event_type("HR Round") == EventType.HR_ROUND
    assert classify_event_type("Pre-Placement Talk") == EventType.PRE_PLACEMENT_TALK
    assert classify_event_type("Interview") == EventType.INTERVIEW
    assert classify_event_type("Something unrecognized") == EventType.OTHER


def test_dedupe_key_is_stable_across_formatting_differences():
    """The whole point of the dedupe key: the same real-world event,
    described with different casing/whitespace/date format, must produce an
    identical key so the DB's unique constraint actually catches it."""
    key1 = compute_dedupe_key("Acme Corp", EventType.TECHNICAL_ROUND, date(2026, 8, 25), "10:30")
    key2 = compute_dedupe_key(" acme corp ", EventType.TECHNICAL_ROUND, date(2026, 8, 25), "10:30")
    assert key1 == key2


def test_dedupe_key_differs_for_a_genuinely_different_event():
    key1 = compute_dedupe_key("Acme Corp", EventType.TECHNICAL_ROUND, date(2026, 8, 25), "10:30")
    key2 = compute_dedupe_key("Acme Corp", EventType.HR_ROUND, date(2026, 8, 25), "10:30")
    assert key1 != key2


def test_an_unparseable_date_degrades_to_none_not_a_crash():
    event = extract_event({"company": "Acme", "event_date": "sometime next week maybe"})
    assert event is not None
    assert event.event_date is None
