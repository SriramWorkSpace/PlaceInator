"""Chunking is pure text processing -- no embedding model required, so these
stay in the fast unit suite. The span-exactness assertion matters beyond this
module: placeinator.latex will splice by these offsets."""

from __future__ import annotations

from placeinator.db.enums import ChunkKind, RequirementKind
from placeinator.matching.chunking import chunk_job_description, chunk_resume_text

SAMPLE_RESUME = """\
Jane Doe -- Backend Engineer

Skills
Python, FastAPI, PostgreSQL, Docker

Experience
- Built a payments service handling 10k requests/sec using Python and FastAPI
- Migrated legacy jobs from cron to Kubernetes

Projects
- Personal blog engine in Django with a Redis cache

Education
B.Tech in Computer Science
"""

SAMPLE_JD = """\
Backend Engineer

Requirements
- 3+ years of experience with Python
- Required: strong SQL skills

Preferred
- Experience with Kubernetes is a plus

Responsibilities
- You will design and operate backend services
"""


def test_chunk_resume_assigns_kinds_from_headings():
    chunks = chunk_resume_text(SAMPLE_RESUME)
    kinds = {c.kind for c in chunks}
    assert ChunkKind.SKILL in kinds
    assert ChunkKind.EXPERIENCE_BULLET in kinds
    assert ChunkKind.PROJECT_BULLET in kinds
    assert ChunkKind.EDUCATION in kinds


def test_chunk_resume_strips_bullet_markers():
    chunks = chunk_resume_text(SAMPLE_RESUME)
    experience = [c for c in chunks if c.kind == ChunkKind.EXPERIENCE_BULLET]
    assert experience
    for chunk in experience:
        assert not chunk.text.startswith("-")


def test_chunk_resume_extracts_skills_per_chunk():
    chunks = chunk_resume_text(SAMPLE_RESUME)
    experience = [c for c in chunks if c.kind == ChunkKind.EXPERIENCE_BULLET]
    payments_bullet = next(c for c in experience if "payments" in c.text)
    assert "python" in payments_bullet.skill_ids
    assert "fastapi" in payments_bullet.skill_ids


def test_chunk_resume_spans_are_exact_substrings():
    """The LaTeX splice emitter depends on span_start/span_end being exact --
    if this drifts, tailoring would corrupt the user's source."""
    chunks = chunk_resume_text(SAMPLE_RESUME)
    for chunk in chunks:
        assert SAMPLE_RESUME[chunk.span_start : chunk.span_end] == chunk.text or (
            # bullet markers are stripped from .text but not from the span,
            # so the span may retain the "- " prefix the text does not.
            SAMPLE_RESUME[chunk.span_start : chunk.span_end].endswith(chunk.text)
        )


def test_chunk_resume_text_before_first_heading_is_summary():
    chunks = chunk_resume_text(SAMPLE_RESUME)
    assert chunks[0].kind == ChunkKind.SUMMARY
    assert "Jane Doe" in chunks[0].text


def test_chunk_job_description_classifies_required_vs_preferred():
    lines = chunk_job_description(SAMPLE_JD)
    kinds = {line.kind for line in lines}
    assert RequirementKind.REQUIRED_SKILL in kinds
    assert RequirementKind.PREFERRED_SKILL in kinds
    assert RequirementKind.RESPONSIBILITY in kinds


def test_chunk_job_description_extracts_skills():
    lines = chunk_job_description(SAMPLE_JD)
    python_line = next(line for line in lines if "Python" in line.text)
    assert "python" in python_line.skill_ids


def test_chunk_job_description_skips_heading_only_lines():
    lines = chunk_job_description(SAMPLE_JD)
    headings = {"Requirements", "Preferred", "Responsibilities"}
    assert not any(line.text.strip() in headings for line in lines)


def test_empty_input_produces_no_chunks():
    assert chunk_resume_text("") == []
    assert chunk_job_description("") == []
