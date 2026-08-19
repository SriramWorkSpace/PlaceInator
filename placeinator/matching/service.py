"""Wires stored resumes and a stored job into placeinator.matching.scoring and
persists the result -- the piece that turns the scoring engine into the "add 3
resumes, paste a JD, get a ranked recommendation" loop M1 is built around."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from placeinator.db.models import Job, JobRequirement, MatchResult, Profile, Resume, ResumeChunk
from placeinator.matching.chunking import RequirementLine, TextChunk
from placeinator.matching.scoring import SCORING_VERSION, score_match


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


def match_resume_to_job(session: Session, resume: Resume, job: Job) -> MatchResult:
    """Score one (resume, job) pair and upsert the MatchResult.

    Re-embeds from the stored chunk/requirement text rather than reusing the
    persisted embedding bytes -- correct and simple for M1's scale. Reusing
    stored vectors is a real optimization path once ranking needs to run over
    hundreds of cached jobs at once (see docs/architecture.md's latency
    budget), but is not required to meet it for a single-job match.
    """
    explanation = score_match(
        resume_chunks=[_chunk_to_domain(c) for c in resume.chunks],
        requirements=[_requirement_to_domain(r) for r in job.requirements],
        resume_target_role=resume.target_role,
        jd_title=job.designation,
    )

    result = session.execute(
        select(MatchResult).where(
            MatchResult.job_id == job.id, MatchResult.resume_id == resume.id
        )
    ).scalar_one_or_none()

    if result is None:
        result = MatchResult(job=job, resume_id=resume.id)
        session.add(result)

    result.semantic_score = explanation.semantic_score
    result.personalized_score = explanation.personalized_score
    result.explanation = explanation.to_dict()
    result.scoring_version = SCORING_VERSION

    session.flush()
    return result


def rank_resumes_for_job(session: Session, profile: Profile, job: Job) -> list[MatchResult]:
    """Score every resume in the library against one job and return them best
    first -- the resume-recommendation flow from spec §3."""
    results = [match_resume_to_job(session, resume, job) for resume in profile.resumes]
    results.sort(key=lambda r: r.personalized_score, reverse=True)
    return results
