"""Exercises the real embedding model, so it is opt-in (-m model) rather than
part of the default suite: first run downloads ~130 MB and the whole run takes
seconds, not milliseconds. CI can enable it deliberately; local development
should not pay that cost on every pytest invocation."""

from __future__ import annotations

import pytest

from placeinator.matching.chunking import chunk_job_description, chunk_resume_text
from placeinator.matching.scoring import score_match

pytestmark = pytest.mark.model

STRONG_RESUME = """\
Skills
Python, FastAPI, PostgreSQL, Docker, Kubernetes

Experience
- Built a backend service in Python and FastAPI handling 10k requests/sec
- Deployed services to Kubernetes and managed CI/CD pipelines

Projects
- REST API for a payments platform using FastAPI and PostgreSQL
"""

WEAK_RESUME = """\
Skills
Photoshop, Illustrator, Figma

Experience
- Designed marketing graphics for a retail brand

Projects
- Redesigned a brand's visual identity
"""

JD = """\
Backend Engineer

Requirements
- Required: strong experience with Python
- Required: experience with FastAPI or a similar framework

Responsibilities
- You will design and operate backend REST services
- You will deploy services to Kubernetes
"""


def test_a_matching_resume_scores_higher_than_an_unrelated_one():
    requirements = chunk_job_description(JD)

    strong_score = score_match(
        resume_chunks=chunk_resume_text(STRONG_RESUME),
        requirements=requirements,
        resume_target_role="Backend Engineer",
        jd_title="Backend Engineer",
    )
    weak_score = score_match(
        resume_chunks=chunk_resume_text(WEAK_RESUME),
        requirements=requirements,
        resume_target_role="Graphic Designer",
        jd_title="Backend Engineer",
    )

    assert strong_score.personalized_score > weak_score.personalized_score
    assert strong_score.components["skills"].value > weak_score.components["skills"].value


def test_explanation_serializes_to_a_readable_dict():
    requirements = chunk_job_description(JD)
    result = score_match(
        resume_chunks=chunk_resume_text(STRONG_RESUME),
        requirements=requirements,
        resume_target_role="Backend Engineer",
        jd_title="Backend Engineer",
    )

    explanation = result.to_dict()
    assert set(explanation) == {"overall", "skills", "projects", "experience", "role"}
    for component in explanation.values():
        assert 0.0 <= component["value"] <= 1.0
        assert isinstance(component["evidence"], list)


def test_every_component_score_is_bounded():
    requirements = chunk_job_description(JD)
    result = score_match(
        resume_chunks=chunk_resume_text(STRONG_RESUME),
        requirements=requirements,
        resume_target_role="Backend Engineer",
        jd_title="Backend Engineer",
    )
    for component in result.components.values():
        assert 0.0 <= component.value <= 1.0
    assert 0.0 <= result.personalized_score <= 1.0
