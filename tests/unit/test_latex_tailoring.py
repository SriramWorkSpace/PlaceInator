"""placeinator.latex.tailoring -- scoring, section/bullet ordering, exclusion,
and the persisted TailoredResume row.

Uses hand-crafted one-hot embedding vectors instead of the real model (the
same trick tests/unit/test_matching_cache.py uses) so cosine similarity is
fully controlled and this stays in the fast default suite: a chunk whose
vector points along the same axis as the JD's is a perfect match (1.0), one
on an orthogonal axis is irrelevant (0.0).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from placeinator.db.enums import ChunkKind, RequirementKind, SourceKind
from placeinator.db.models import Job, JobRequirement, Profile, Resume, ResumeChunk, TailoredResume
from placeinator.latex.parsing import BulletGroup, Span, bullet_id, parse_latex
from placeinator.latex.tailoring import tailor_resume
from placeinator.matching.vectors import EMBEDDING_DIM, EMBEDDING_MODEL_NAME, encode_vector

FIXTURES = Path(__file__).parents[1] / "fixtures" / "resumes"


def _unit_vector(axis: int) -> np.ndarray:
    v = np.zeros(EMBEDDING_DIM, dtype=np.float32)
    v[axis] = 1.0
    return v


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def profile(session: Session) -> Profile:
    p = Profile(full_name="A", email="a@example.com")
    session.add(p)
    session.flush()
    return p


def _resume(session: Session, profile: Profile, source_text: str) -> Resume:
    resume = Resume(
        profile_id=profile.id, label="main", source_format="tex", source_text=source_text
    )
    session.add(resume)
    session.flush()
    return resume


def _job(
    session: Session,
    requirement_vector: np.ndarray,
    required_skill_ids: list[str] | None = None,
) -> Job:
    job = Job(
        source=SourceKind.MANUAL,
        company="Acme",
        designation="Backend Engineer",
        description="d",
        required_skill_ids=required_skill_ids or [],
    )
    session.add(job)
    session.flush()
    session.add(
        JobRequirement(
            job_id=job.id,
            kind=RequirementKind.RESPONSIBILITY,
            text="requirement",
            order_index=0,
            skill_ids=[],
            embedding=encode_vector(requirement_vector),
            embedding_model=EMBEDDING_MODEL_NAME,
            embedding_dim=EMBEDDING_DIM,
        )
    )
    session.flush()
    return job


def _chunk(
    session: Session,
    resume: Resume,
    span: Span,
    vector: np.ndarray,
    *,
    skill_ids: list[str] | None = None,
) -> ResumeChunk:
    chunk = ResumeChunk(
        resume_id=resume.id,
        kind=ChunkKind.EXPERIENCE_BULLET,
        text="placeholder",
        order_index=0,
        span_start=span.start,
        span_end=span.end,
        skill_ids=skill_ids or [],
        embedding=encode_vector(vector),
        embedding_model=EMBEDDING_MODEL_NAME,
        embedding_dim=EMBEDDING_DIM,
    )
    session.add(chunk)
    return chunk


def test_the_more_relevant_bullet_moves_first(session, profile):
    source = _read("sde_resume.tex")
    parsed = parse_latex(source)
    experience_idx = next(i for i, s in enumerate(parsed.sections) if s.heading == "Experience")
    group = next(r for r in parsed.sections[experience_idx].regions if isinstance(r, BulletGroup))
    built_bullet, deployed_bullet = group.bullets

    resume = _resume(session, profile, source)
    _chunk(session, resume, built_bullet.span, _unit_vector(1))  # irrelevant
    _chunk(session, resume, deployed_bullet.span, _unit_vector(0))  # perfect match
    session.flush()
    job = _job(session, _unit_vector(0))

    tailored = tailor_resume(session, resume, job)

    experience = next(s for s in tailored.change_log["sections"] if s["heading"] == "Experience")
    assert experience["bullets"][0]["text"].startswith("\\item Deployed")
    assert experience["bullets"][0]["score"] == pytest.approx(1.0)
    assert experience["bullets"][1]["score"] == pytest.approx(0.0)
    # And the emitted .tex actually reflects that order, not just the log.
    assert tailored.tex.index("Deployed") < tailored.tex.index("Built a backend")


def test_a_bullet_with_no_overlapping_chunk_scores_neutral_not_zero(session, profile):
    """No signal must not read as "irrelevant" -- see _score_span's docstring."""
    source = _read("sde_resume.tex")
    resume = _resume(session, profile, source)
    # No ResumeChunk rows at all.
    job = _job(session, _unit_vector(0))

    tailored = tailor_resume(session, resume, job)

    experience = next(s for s in tailored.change_log["sections"] if s["heading"] == "Experience")
    assert all(b["score"] == pytest.approx(0.5) for b in experience["bullets"])


def test_sections_reorder_into_the_canonical_whitelist_not_score(session, profile):
    """Skills before Experience before Projects, per the spec's own tree --
    regardless of source order or relevance."""
    source = _read("sde_resume.tex")  # source order is Skills, Experience, Projects already
    resume = _resume(session, profile, source)
    job = _job(session, _unit_vector(0))

    tailored = tailor_resume(session, resume, job)

    headings_in_new_order = [
        s["heading"] for s in sorted(tailored.change_log["sections"], key=lambda s: s["new_index"])
    ]
    assert headings_in_new_order == ["Skills", "Experience", "Projects"]


def test_an_unrecognized_heading_sorts_after_every_recognized_section(session, profile):
    source = (
        "\\documentclass{article}\n\\begin{document}\n"
        "\\section{Hobbies}\nChess\n"
        "\\section{Skills}\nPython\n"
        "\\end{document}\n"
    )
    resume = _resume(session, profile, source)
    job = _job(session, _unit_vector(0))

    tailored = tailor_resume(session, resume, job)

    headings_in_new_order = [
        s["heading"] for s in sorted(tailored.change_log["sections"], key=lambda s: s["new_index"])
    ]
    assert headings_in_new_order == ["Skills", "Hobbies"]


def test_excluding_a_bullet_drops_it_from_the_emitted_tex(session, profile):
    source = _read("sde_resume.tex")
    parsed = parse_latex(source)
    experience_idx = next(i for i, s in enumerate(parsed.sections) if s.heading == "Experience")
    group = next(r for r in parsed.sections[experience_idx].regions if isinstance(r, BulletGroup))

    resume = _resume(session, profile, source)
    for bullet in group.bullets:
        _chunk(session, resume, bullet.span, _unit_vector(0))
    session.flush()
    job = _job(session, _unit_vector(0))

    excluded_id = bullet_id(group.bullets[0])
    tailored = tailor_resume(session, resume, job, excluded_bullet_ids=frozenset({excluded_id}))

    assert "Built a backend service" not in tailored.tex
    assert "Deployed services" in tailored.tex


def test_a_low_scoring_bullet_is_suggested_not_removed(session, profile):
    source = _read("sde_resume.tex")
    parsed = parse_latex(source)
    experience_idx = next(i for i, s in enumerate(parsed.sections) if s.heading == "Experience")
    group = next(r for r in parsed.sections[experience_idx].regions if isinstance(r, BulletGroup))

    resume = _resume(session, profile, source)
    _chunk(session, resume, group.bullets[0].span, _unit_vector(1))  # irrelevant -> low score
    _chunk(session, resume, group.bullets[1].span, _unit_vector(0))
    session.flush()
    job = _job(session, _unit_vector(0))

    tailored = tailor_resume(session, resume, job)

    experience = next(s for s in tailored.change_log["sections"] if s["heading"] == "Experience")
    low_scoring = next(b for b in experience["bullets"] if b["score"] < 0.35)
    assert low_scoring["suggested_removal"] is True
    # Suggested, never auto-dropped -- the content survives unless the
    # caller explicitly excludes it.
    assert "Built a backend service" in tailored.tex


def test_requirement_coverage_is_a_set_difference_over_existing_skill_ids(session, profile):
    source = _read("sde_resume.tex")
    parsed = parse_latex(source)
    experience_idx = next(i for i, s in enumerate(parsed.sections) if s.heading == "Experience")
    group = next(r for r in parsed.sections[experience_idx].regions if isinstance(r, BulletGroup))

    resume = _resume(session, profile, source)
    _chunk(session, resume, group.bullets[0].span, _unit_vector(0), skill_ids=["python", "fastapi"])
    session.flush()
    job = _job(session, _unit_vector(0), required_skill_ids=["python", "fastapi", "docker"])

    tailored = tailor_resume(session, resume, job)

    assert sorted(tailored.change_log["requirements_matched"]) == ["fastapi", "python"]
    assert tailored.change_log["requirements_missing"] == ["docker"]


def test_repeated_tailoring_upserts_the_same_row_not_a_duplicate(session, profile):
    source = _read("sde_resume.tex")
    resume = _resume(session, profile, source)
    job = _job(session, _unit_vector(0))

    first = tailor_resume(session, resume, job)
    second = tailor_resume(session, resume, job)

    assert first.id == second.id

    count = session.execute(
        select(func.count()).select_from(TailoredResume).where(
            TailoredResume.resume_id == resume.id, TailoredResume.job_id == job.id
        )
    ).scalar_one()
    assert count == 1


def test_a_section_mixing_an_empty_custom_macro_group_and_a_real_group_does_not_misattach_orders(
    session, profile
):
    """Regression test for a real bug caught during development: emit_latex
    increments its group index on every BulletGroup (empty or not), so
    tailor_resume's own counting has to match exactly, or a score-based order
    computed for the second (real) group would attach to the first (empty)
    one -- which crashes with an IndexError the moment emit_latex tries to
    index into an empty bullets tuple."""
    source = _read("mixed_bullet_groups.tex")
    parsed = parse_latex(source)
    section = parsed.sections[0]
    groups = [r for r in section.regions if isinstance(r, BulletGroup)]
    assert groups[0].bullets == ()  # precondition: first group is the empty one
    real_group = groups[1]

    resume = _resume(session, profile, source)
    _chunk(session, resume, real_group.bullets[0].span, _unit_vector(1))
    _chunk(session, resume, real_group.bullets[1].span, _unit_vector(0))
    session.flush()
    job = _job(session, _unit_vector(0))

    tailored = tailor_resume(session, resume, job)  # must not raise

    bullets = tailored.change_log["sections"][0]["bullets"]
    assert len(bullets) == 2
    assert bullets[0]["text"].startswith("\\item Recognized bullet two")
