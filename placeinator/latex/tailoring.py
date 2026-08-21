"""Orchestrates JD-based LaTeX resume tailoring (specification section 5):
scores each movable unit found by ``placeinator.latex.parsing`` against a
job, reorders sections into a canonical whitelist and bullets by relevance,
emits the new ``.tex``, and upserts a ``TailoredResume`` row.

Reuses M1/M2 infrastructure end to end rather than a parallel pipeline:

* Relevance scoring pools the *same* persisted ``ResumeChunk``/
  ``JobRequirement`` embedding vectors ``placeinator.matching.service``
  already caches, via the same ``mean_pool``/``clamp_unit`` primitives
  ``placeinator.matching.scoring`` uses for its ``overall`` component.
* Requirement coverage ("matched"/"missing") is a set difference over
  ``Job.required_skill_ids`` and the union of ``ResumeChunk.skill_ids`` --
  both already computed and stored, not re-extracted here.

Every call recomputes and overwrites the ``(resume_id, job_id)``
``TailoredResume`` row. Unlike ``MatchResult``, there is no freshness gate to
bypass: tailoring is user-triggered on demand, not polled on every Dashboard
mount, so "recompute every time it's asked for" is already cheap enough.

Removal is never automatic (spec: "Removals require explicit confirmation...
never silent"). A bullet scoring below ``_SUGGEST_REMOVAL_BELOW`` is flagged
as a *suggestion* only; the emitted ``.tex`` still contains it unless its id
appears in the caller's own ``excluded_bullet_ids``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from placeinator.db.enums import ChunkKind
from placeinator.db.models import Job, Resume, ResumeChunk, TailoredResume
from placeinator.latex.parsing import BulletGroup, Span, bullet_id, emit_latex, parse_latex
from placeinator.matching.chunking import classify_heading
from placeinator.matching.scoring import clamp_unit, mean_pool
from placeinator.matching.service import stored_vectors
from placeinator.matching.vectors import EMBEDDING_DIM, embed_texts

# The spec's own section tree (specification.md section 5's "LaTeX Resume
# Analysis" diagram) -- sections reorder into this canonical whitelist, never
# by score (that's architecture.md's "permitted whitelist order"). A heading
# that doesn't classify into one of these keeps its relative position among
# other unrecognized headings, sorted after every recognized section.
_CANONICAL_SECTION_ORDER: tuple[ChunkKind, ...] = (
    ChunkKind.SUMMARY,
    ChunkKind.EDUCATION,
    ChunkKind.SKILL,
    ChunkKind.EXPERIENCE_BULLET,
    ChunkKind.PROJECT_BULLET,
    ChunkKind.CERTIFICATION,
    ChunkKind.ACHIEVEMENT,
)

# Below this, a bullet is *suggested* for removal -- never removed
# automatically. Same neutral-midpoint convention as _score_skills'/
# _score_role's "no signal" default in placeinator.matching.scoring.
_SUGGEST_REMOVAL_BELOW = 0.35


@dataclass(frozen=True)
class BulletScore:
    bullet_id: int
    text: str
    original_index: int
    new_index: int
    score: float
    suggested_removal: bool
    excluded: bool


@dataclass(frozen=True)
class SectionResult:
    heading: str
    original_index: int
    new_index: int
    bullets: tuple[BulletScore, ...]


@dataclass(frozen=True)
class TailoringResult:
    tex: str
    sections: tuple[SectionResult, ...]
    requirements_matched: tuple[str, ...]
    requirements_missing: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "sections": [
                {
                    "heading": s.heading,
                    "original_index": s.original_index,
                    "new_index": s.new_index,
                    "bullets": [
                        {
                            "bullet_id": b.bullet_id,
                            "text": b.text,
                            "original_index": b.original_index,
                            "new_index": b.new_index,
                            "score": b.score,
                            "suggested_removal": b.suggested_removal,
                            "excluded": b.excluded,
                        }
                        for b in s.bullets
                    ],
                }
                for s in self.sections
            ],
            "requirements_matched": list(self.requirements_matched),
            "requirements_missing": list(self.requirements_missing),
        }


def _overlapping_chunks(chunks: list[ResumeChunk], span: Span) -> list[ResumeChunk]:
    return [
        c
        for c in chunks
        if c.span_start is not None
        and c.span_end is not None
        and c.span_start < span.end
        and c.span_end > span.start
    ]


def _span_vector(chunks: list[ResumeChunk]) -> np.ndarray | None:
    """Mean-pooled vector for a set of overlapping chunks, reusing their
    persisted embeddings and falling back to a fresh embed only if a stamp
    doesn't match -- the same resilience pattern
    ``placeinator.matching.service.match_resume_to_job`` uses. ``None`` when
    there is nothing to pool (the caller treats this as "no signal")."""
    if not chunks:
        return None
    vectors = stored_vectors(chunks)
    if vectors is None:
        vectors = embed_texts([c.text for c in chunks])
    return mean_pool(vectors)


def _score_span(span: Span, chunks: list[ResumeChunk], jd_vector: np.ndarray) -> float:
    """Relevance of one movable unit against the JD: cosine of its
    overlapping resume chunks' mean-pooled vector against the JD's mean
    vector -- the same primitive ``_score_overall`` uses for the whole
    resume. Neutral (0.5) when nothing overlaps, never a bare 0.0, which
    would misleadingly read as "irrelevant" rather than "unmeasured"."""
    unit_vector = _span_vector(_overlapping_chunks(chunks, span))
    if unit_vector is None:
        return 0.5
    return clamp_unit(float(np.dot(unit_vector, jd_vector)))


def _jd_vector(job: Job) -> np.ndarray:
    requirement_rows = list(job.requirements)
    if not requirement_rows:
        return np.zeros(EMBEDDING_DIM, dtype=np.float32)
    vectors = stored_vectors(requirement_rows)
    if vectors is None:
        vectors = embed_texts([r.text for r in requirement_rows])
    return mean_pool(vectors)


def _section_sort_key(heading: str, original_index: int) -> tuple[int, int]:
    kind = classify_heading(heading)
    if kind is not None and kind in _CANONICAL_SECTION_ORDER:
        return (_CANONICAL_SECTION_ORDER.index(kind), original_index)
    return (len(_CANONICAL_SECTION_ORDER), original_index)


def _requirement_coverage(
    job: Job, chunks: list[ResumeChunk]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    resume_skills: set[str] = set()
    for chunk in chunks:
        resume_skills |= set(chunk.skill_ids)

    required = set(job.required_skill_ids)
    matched = tuple(sorted(required & resume_skills))
    missing = tuple(sorted(required - resume_skills))
    return matched, missing


def tailor_resume(
    session: Session,
    resume: Resume,
    job: Job,
    *,
    excluded_bullet_ids: frozenset[int] = frozenset(),
) -> TailoredResume:
    parsed = parse_latex(resume.source_text)
    chunks = list(resume.chunks)
    jd_vector = _jd_vector(job)

    section_order = sorted(
        range(len(parsed.sections)),
        key=lambda i: _section_sort_key(parsed.sections[i].heading, i),
    )

    bullet_orders: dict[int, dict[int, list[int]]] = {}
    section_results: list[SectionResult] = []

    for new_section_index, section_index in enumerate(section_order):
        section = parsed.sections[section_index]
        bullet_scores: list[BulletScore] = []
        # Must match emit_latex's own group-index counting exactly -- both
        # increment on every BulletGroup, empty or not, or a bullet order
        # would attach to the wrong group in a section that mixes an empty
        # custom-macro list with a real itemize.
        group_index = 0
        for region in section.regions:
            if not isinstance(region, BulletGroup):
                continue
            if region.bullets:
                scored = sorted(
                    (
                        (i, _score_span(b.span, chunks, jd_vector))
                        for i, b in enumerate(region.bullets)
                    ),
                    key=lambda t: t[1],
                    reverse=True,
                )
                bullet_orders.setdefault(section_index, {})[group_index] = [i for i, _ in scored]

                for new_bullet_index, (bullet_index, score) in enumerate(scored):
                    bullet = region.bullets[bullet_index]
                    bid = bullet_id(bullet)
                    bullet_scores.append(
                        BulletScore(
                            bullet_id=bid,
                            text=parsed.text(bullet.span).strip(),
                            original_index=bullet_index,
                            new_index=new_bullet_index,
                            score=score,
                            suggested_removal=score < _SUGGEST_REMOVAL_BELOW,
                            excluded=bid in excluded_bullet_ids,
                        )
                    )
            group_index += 1

        section_results.append(
            SectionResult(
                heading=section.heading,
                original_index=section_index,
                new_index=new_section_index,
                bullets=tuple(bullet_scores),
            )
        )

    tex = emit_latex(
        parsed,
        section_order=section_order,
        bullet_orders=bullet_orders,
        excluded_bullet_ids=excluded_bullet_ids,
    )
    matched, missing = _requirement_coverage(job, chunks)
    result_data = TailoringResult(
        tex=tex,
        sections=tuple(section_results),
        requirements_matched=matched,
        requirements_missing=missing,
    )

    tailored = session.execute(
        select(TailoredResume).where(
            TailoredResume.resume_id == resume.id, TailoredResume.job_id == job.id
        )
    ).scalar_one_or_none()
    if tailored is None:
        tailored = TailoredResume(resume_id=resume.id, job_id=job.id)
        session.add(tailored)

    tailored.tex = tex
    tailored.change_log = result_data.to_dict()
    tailored.excluded_bullet_ids = sorted(excluded_bullet_ids)

    session.flush()
    return tailored
