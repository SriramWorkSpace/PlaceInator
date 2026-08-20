"""placeinator.resumes.extraction -- regex/heuristic autofill, not a parser.

Every assertion here is either "this obvious pattern is found" or "this absent
pattern stays null" -- the extractor must never guess.
"""

from __future__ import annotations

from placeinator.resumes.extraction import extract_profile_fields

RESUME_TEXT = """\
Jane Doe
jane.doe@example.com | +1 415-555-0199

Education
B.Tech in Computer Science, Stanford University, 2024

Skills
Python, FastAPI, PostgreSQL
"""


def test_extracts_all_fields_from_a_well_formed_header():
    fields = extract_profile_fields(RESUME_TEXT)

    assert fields.full_name == "Jane Doe"
    assert fields.email == "jane.doe@example.com"
    assert fields.phone == "+1 415-555-0199"
    assert fields.college == "B.Tech in Computer Science, Stanford University, 2024"
    assert fields.department == "Computer Science"


def test_missing_fields_stay_null_rather_than_guessed():
    fields = extract_profile_fields(
        "Highly motivated software engineer with five years of experience.\n"
        "Skills: Python, Docker, Kubernetes.\n"
    )

    assert fields.full_name is None
    assert fields.email is None
    assert fields.phone is None
    assert fields.college is None
    assert fields.department is None


def test_name_line_is_skipped_when_it_contains_contact_info_or_is_a_heading():
    fields = extract_profile_fields("jane.doe@example.com\nSummary\nBackend engineer.")
    assert fields.full_name is None
    assert fields.email == "jane.doe@example.com"


def test_short_digit_runs_are_not_mistaken_for_a_phone_number():
    fields = extract_profile_fields("Graduated 2024\nGPA 3.9\n")
    assert fields.phone is None


def test_college_matched_by_institution_keyword():
    fields = extract_profile_fields("Indian Institute of Technology, Bombay\n")
    assert fields.college == "Indian Institute of Technology, Bombay"
