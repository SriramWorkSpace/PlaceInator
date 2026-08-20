"""placeinator.jobs.extraction -- regex/heuristic autofill, not a parser.

A JD's layout is far less standardized than a resume's, so most of what
matters here is that the extractor stays conservative rather than guessing.
"""

from __future__ import annotations

from placeinator.jobs.extraction import extract_job_fields

JD_TEXT = """\
Senior Backend Engineer

Company: Acme Corp

About the role
We are looking for an experienced backend engineer to join our platform team.

Requirements
- 5+ years of experience with Python
- Strong understanding of distributed systems
"""


def test_extracts_designation_and_labeled_company():
    fields = extract_job_fields(JD_TEXT)
    assert fields.designation == "Senior Backend Engineer"
    assert fields.company == "Acme Corp"


def test_about_company_line_is_recognized():
    fields = extract_job_fields("Backend Engineer\n\nAbout Acme Corp\nWe build things.\n")
    assert fields.company == "Acme Corp"


def test_missing_company_stays_null_rather_than_guessed():
    fields = extract_job_fields(
        "Backend Engineer\n\nWe are hiring a backend engineer for our team.\n"
    )
    assert fields.designation == "Backend Engineer"
    assert fields.company is None


def test_long_first_line_is_not_mistaken_for_a_title():
    fields = extract_job_fields(
        "We are a fast-growing startup looking for talented engineers to join us.\n"
        "Company: Acme Corp\n"
    )
    assert fields.designation is None
    assert fields.company == "Acme Corp"
