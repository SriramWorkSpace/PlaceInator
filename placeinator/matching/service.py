"""Wires stored resumes and a stored job into placeinator.matching.scoring and
persists the result -- the piece that turns the scoring engine into the "add 3
resumes, paste a JD, get a ranked recommendation" loop M1 is built around."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from placeinator.db.models import Job, JobRequirement, MatchResult, Profile, Resume, ResumeChunk
from placeinator.matching.chunking import RequirementLine, TextChunk
from placeinator.matching.scoring import SCORING_VERSION, score_match
from placeinator.matching.vectors import (
    EMBEDDING_DIM,
    EMBEDDING_MODEL_NAME,
    decode_vector,
)


def _as_naive_utc(value: datetime) -> datetime:
    """TimestampMixin fills these from two different places -- a SQL
    ``server_default`` on insert, a Python ``onupdate`` on update -- so a row
    just written in this session holds a tz-aware value in memory while one
    loaded from SQLite is naive UTC. Comparing the two raises TypeError, and
    ``match_resume_to_job`` flushes rather than commits, so both shapes are
    genuinely in play at once. Normalize before comparing.
    """
    return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value


def _stored_vectors(rows: list[ResumeChunk] | list[JobRequirement]) -> np.ndarray | None:
    """The persisted embeddings for these rows, or ``None`` if any of them
    can't be trusted.

    Every row stamps ``embedding_model``/``embedding_dim`` alongside the bytes
    precisely so a model change leaves them detectable rather than silently
    deserializing into meaningless numbers (see placeinator.matching.vectors).
    ``None`` means "re-embed from text", which is always correct, just slower.
    """
    if not rows:
        return np.zeros((0, EMBEDDING_DIM), dtype=np.float32)

    vectors = []
    for row in rows:
        if (
            row.embedding is None
            or row.embedding_model != EMBEDDING_MODEL_NAME
            or row.embedding_dim != EMBEDDING_DIM
        ):
            return None
        vectors.append(decode_vector(row.embedding))
    return np.vstack(vectors)


def _is_fresh(result: MatchResult, job: Job, resume: Resume) -> bool:
    """Whether a stored MatchResult can be reused instead of rescored.

    Stale on a scoring-version bump, or if either side has been written since
    the score was taken. Timestamps err toward recomputing: an insert records
    whole seconds (SQLite's CURRENT_TIMESTAMP) while an update carries
    microseconds, so a tie reads as "recompute", never as a stale hit.

    Note this only invalidates on a *real* change. SQLAlchemy doesn't issue an
    UPDATE when an assignment doesn't alter the value, so re-running
    ``refilter_jobs`` over unchanged preferences leaves the cache intact.
    """
    if result.scoring_version != SCORING_VERSION:
        return False
    taken_at = _as_naive_utc(result.updated_at)
    return taken_at >= _as_naive_utc(job.updated_at) and taken_at >= _as_naive_utc(
        resume.updated_at
    )


def _chunk_to_domain(row: ResumeChunk) -> TextChunk:
    return TextChunk(
        kind=row.kind,
        section=row.section,
        text=row.text,
        span_start=row.span_start or 0,
        span_end=row.span_end or 0,
        skill_ids=frozenset(row.skill_ids),
    )


def _requirement_to_domain(row: JobRequirement) -> RequirementLine:
    return RequirementLine(kind=row.kind, text=row.text, skill_ids=frozenset(row.skill_ids))


def match_resume_to_job(
    session: Session, resume: Resume, job: Job, *, use_cache: bool = True
) -> MatchResult:
    """Score one (resume, job) pair and upsert the MatchResult.

    The stored MatchResult *is* the cache: a row that is still fresh (see
    ``_is_fresh``) is returned as-is, touching neither the embedding model nor
    the scoring math. This is what keeps ranking a whole corpus cheap --
    ``rank_jobs`` calls this once per job on every Dashboard mount, and
    without it each of those re-embedded every chunk and requirement.

    When a rescore *is* needed, it reuses the embeddings already persisted on
    the chunk and requirement rows, so even the cold path usually embeds
    nothing beyond the two short role strings.

    Pass ``use_cache=False`` to force a rescore.
    """
    result = session.execute(
        select(MatchResult).where(
            MatchResult.job_id == job.id, MatchResult.resume_id == resume.id
        )
    ).scalar_one_or_none()

    if use_cache and result is not None and _is_fresh(result, job, resume):
        return result

    chunk_rows = list(resume.chunks)
    requirement_rows = list(job.requirements)

    explanation = score_match(
        resume_chunks=[_chunk_to_domain(c) for c in chunk_rows],
        requirements=[_requirement_to_domain(r) for r in requirement_rows],
        resume_target_role=resume.target_role,
        jd_title=job.designation,
        resume_vectors=_stored_vectors(chunk_rows),
        requirement_vectors=_stored_vectors(requirement_rows),
    )

    if result is None:
        result = MatchResult(job=job, resume_id=resume.id)
        session.add(result)

    result.semantic_score = explanation.semantic_score
    result.personalized_score = explanation.personalized_score
    result.explanation = explanation.to_dict()
    result.scoring_version = SCORING_VERSION
    # Touched explicitly rather than left to `onupdate`, which only fires when
    # a value actually changes. A rescore triggered by a change that doesn't
    # move the scores (a re-filtered job, say) would otherwise leave the row
    # looking stale forever and rescore on every single mount.
    result.updated_at = datetime.now(UTC)

    session.flush()
    return result


def rank_resumes_for_job(session: Session, profile: Profile, job: Job) -> list[MatchResult]:
    """Score every resume in the library against one job and return them best
    first -- the resume-recommendation flow from spec §3."""
    results = [match_resume_to_job(session, resume, job) for resume in profile.resumes]
    results.sort(key=lambda r: r.personalized_score, reverse=True)
    return results
