"""Job intake and persistence.

Two paths share one persistence core (`_apply_requirements`):

* Manual paste (spec section 5's JD paste, doubling as the section-2
  `manual` source -- ADR 0003) -- always available, no source_ref, never
  deduplicated because a pasted JD has no natural identity to dedupe on.
* Adapter ingestion (`upsert_job_from_posting`) -- used by ats_feed today
  and by indeed/linkedin/naukri once they land. Upserts on
  (source, source_ref) so a rescan updates a posting in place rather than
  creating a duplicate every time the same company board is synced again.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from placeinator.db.enums import RequirementKind, SourceKind
from placeinator.db.models import Job, JobRequirement
from placeinator.jobs.sources.ats_feed import AtsFeedSource
from placeinator.jobs.sources.base import RawPosting, SearchQuery, SourceBlocked
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
    deadline: date | None = None,
) -> Job:
    """Persist a pasted job description, chunked and embedded exactly like a
    resume, so placeinator.matching.scoring can score the two symmetrically."""
    job = Job(
        source=SourceKind.MANUAL,
        company=company,
        designation=designation,
        location=location,
        url=url,
        deadline=deadline,
        description=description,
    )
    session.add(job)
    _apply_requirements(session, job, description)
    session.flush()
    return job


def upsert_job_from_posting(session: Session, source: SourceKind, posting: RawPosting) -> Job:
    """Create or update the Job for one adapter-found posting, keyed on
    (source, source_ref) -- Job.source_ref carries the UNIQUE constraint
    that makes this an upsert rather than an insert."""
    existing = session.execute(
        select(Job).where(Job.source == source, Job.source_ref == posting.source_ref)
    ).scalar_one_or_none()

    job = existing or Job(source=source, source_ref=posting.source_ref)
    if existing is None:
        session.add(job)
    else:
        # Re-chunking replaces requirements wholesale; stale ones from a
        # prior scan must not linger alongside the new set.
        for requirement in list(job.requirements):
            session.delete(requirement)

    job.company = posting.company
    job.designation = posting.designation
    job.location = posting.location
    job.url = posting.url
    job.work_mode = posting.work_mode
    job.job_type = posting.job_type
    job.deadline = posting.deadline
    job.description = posting.description

    _apply_requirements(session, job, posting.description)
    session.flush()
    return job


def sync_ats_feed(session: Session, companies: list[str]) -> list[Job] | SourceBlocked:
    """Fetch every "platform:company-slug" entry and upsert the results.

    All-or-nothing per ADR 0003: AtsFeedSource.fetch stops at the first
    blocked company rather than silently skipping it, so a caller always
    knows exactly which entry failed rather than guessing from a partial
    list.
    """
    with AtsFeedSource() as source:
        result = source.fetch(SearchQuery(companies=tuple(companies)))

    if isinstance(result, SourceBlocked):
        return result

    return [upsert_job_from_posting(session, SourceKind.ATS_FEED, posting) for posting in result]


def _apply_requirements(session: Session, job: Job, description: str) -> None:
    """Chunk, embed, and attach requirements; sets required/preferred skill
    ids on the job. Shared by both intake paths so scoring never has to
    care which one produced a given Job."""
    requirement_lines = chunk_job_description(description)
    if not requirement_lines:
        job.required_skill_ids = []
        job.preferred_skill_ids = []
        return

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
