"""Manual job intake (spec section 5's JD paste, doubling as the section-2
`manual` source -- see ADR 0003). Adapter-based discovery lands in M2; this is
the always-available path everything else falls back to."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from placeinator.db.enums import RequirementKind, SourceKind
from placeinator.db.models import Job, JobRequirement
from placeinator.matching.chunking import chunk_job_description
from placeinator.matching.vectors import (
    EMBEDDING_DIM,
    EMBEDDING_MODEL_NAME,
    embed_texts,
    encode_vector,
)


def list_jobs(session: Session) -> list[Job]:
    stmt = select(Job).order_by(Job.created_at.desc())
    return list(session.execute(stmt).scalars())


def create_manual_job(
    session: Session,
    *,
    company: str,
    designation: str,
    description: str,
    location: str | None = None,
    url: str | None = None,
) -> Job:
    """Persist a pasted job description, chunked and embedded exactly like a
    resume, so placeinator.matching.scoring can score the two symmetrically."""
    job = Job(
        source=SourceKind.MANUAL,
        company=company,
        designation=designation,
        location=location,
        url=url,
        description=description,
    )
    session.add(job)

    requirement_lines = chunk_job_description(description)
    if requirement_lines:
        vectors = embed_texts([r.text for r in requirement_lines])
        required_skills: set[str] = set()
        preferred_skills: set[str] = set()
        for order_index, (line, vector) in enumerate(zip(requirement_lines, vectors, strict=True)):
            session.add(
                JobRequirement(
                    job=job,
                    kind=line.kind,
                    text=line.text,
                    order_index=order_index,
                    skill_ids=sorted(line.skill_ids),
                    embedding=encode_vector(vector),
                    embedding_model=EMBEDDING_MODEL_NAME,
                    embedding_dim=EMBEDDING_DIM,
                )
            )

            if line.kind == RequirementKind.REQUIRED_SKILL:
                required_skills |= line.skill_ids
            elif line.kind == RequirementKind.PREFERRED_SKILL:
                preferred_skills |= line.skill_ids

        job.required_skill_ids = sorted(required_skills)
        job.preferred_skill_ids = sorted(preferred_skills)

    session.flush()
    return job
