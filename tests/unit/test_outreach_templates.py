"""placeinator.outreach.templates.render_cold_email -- pure Jinja2 rendering,
no session/DB. Asserts real evidence text appears verbatim (never
paraphrased) and that optional fields degrade gracefully rather than
leaking "None" or leaving double blank lines when omitted.
"""

from __future__ import annotations

from placeinator.outreach.templates import render_cold_email


def _render(**overrides):
    defaults = dict(
        full_name="Jane Doe",
        email="jane@example.com",
        phone="555-1234",
        target_role="Backend Engineer",
        company="Acme Corp",
        designation="Senior Backend Engineer",
        location="Remote",
        highlights=["Built a payments API handling 10k req/sec"],
        matched_skills=["python", "kubernetes"],
    )
    return render_cold_email(**{**defaults, **overrides})


def test_subject_names_the_real_role_and_company():
    result = _render(designation="Staff Engineer", company="Globex")
    assert result.subject == "Application for Staff Engineer at Globex"


def test_a_real_resume_bullet_appears_verbatim_not_paraphrased():
    bullet = "Migrated the payments service from Rails to Go, cutting p99 latency 40%"
    result = _render(highlights=[bullet])
    assert bullet in result.body


def test_matched_skills_are_named_verbatim():
    result = _render(matched_skills=["rust", "distributed-systems"])
    assert "rust, distributed-systems" in result.body


def test_no_highlights_omits_the_section_entirely_not_an_empty_one():
    result = _render(highlights=[])
    assert "directly relevant" not in result.body


def test_no_matched_skills_omits_that_sentence_entirely():
    result = _render(matched_skills=[])
    assert "lines up closely" not in result.body


def test_missing_optional_fields_never_render_as_the_literal_string_none():
    result = _render(email=None, phone=None, target_role=None, location=None)
    assert "None" not in result.body
    assert "None" not in result.subject


def test_missing_optional_fields_leave_no_double_blank_line():
    result = _render(email=None, phone=None, target_role=None, location=None, highlights=[])
    assert "\n\n\n" not in result.body


def test_email_and_phone_appear_verbatim_when_present():
    result = _render(email="jane@corp.com", phone="+1-202-555-0199")
    assert "jane@corp.com" in result.body
    assert "+1-202-555-0199" in result.body
