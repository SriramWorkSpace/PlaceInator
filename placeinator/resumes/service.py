"""Resume persistence: parse, chunk, embed, store.

Every chunk is embedded and stamped with its provenance (embedding_model,
embedding_dim) per the encoding contract in placeinator.matching.vectors, so a
future model change leaves stale rows detectable rather than silently wrong.
"""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from placeinator.db.models import Profile, Resume, ResumeChunk
from placeinator.matching.chunking import chunk_resume_text
from placeinator.matching.vectors import (
    EMBEDDING_DIM,
    EMBEDDING_MODEL_NAME,
    embed_texts,
    encode_vector,
)
from placeinator.resumes.extraction import ExtractedProfileFields, extract_profile_fields
from placeinator.resumes.parsing import SourceFormat, parse_resume_bytes


class ResumeNotFoundError(ValueError):
    """Raised when a resume_id doesn't exist, or belongs to a different profile
    (single-user app, but still a real distinct-row check, not an ownership
    check we can skip)."""


def list_resumes(session: Session, profile: Profile) -> list[Resume]:
    stmt = select(Resume).where(Resume.profile_id == profile.id).order_by(Resume.label)
    return list(session.execute(stmt).scalars())


def extract_profile_preview(
    source_format: SourceFormat, file_bytes: bytes
) -> ExtractedProfileFields:
    """Parse an uploaded file far enough to prefill the onboarding form --
    no DB write. The same file is re-uploaded via create_resume once the user
    confirms/edits the fields and submits."""
    source_text = parse_resume_bytes(file_bytes, source_format)
    return extract_profile_fields(source_text)


def create_resume(
    session: Session,
    profile: Profile,
    *,
    label: str,
    target_role: str | None,
    job_category: str | None,
    source_format: SourceFormat,
    file_bytes: bytes,
    is_primary: bool = False,
) -> Resume:
    """Parse an uploaded file, chunk it, embed every chunk, and persist all of
    it as one Resume with its ResumeChunk children.

    Versioning follows spec §3 ("Each resume can have ... Version"): a resume
    is identified by (profile, label); re-uploading the same label creates the
    next version rather than overwriting history.

    A profile's very first resume is always primary, regardless of the
    is_primary argument -- the Resume Library must never show zero primaries
    once any resume exists. Otherwise is_primary follows the caller.
    """
    source_text = parse_resume_bytes(file_bytes, source_format)

    is_first_resume = not _profile_has_any_resume(session, profile)
    make_primary = is_primary or is_first_resume
    if make_primary:
        _clear_existing_primary(session, profile)

    next_version = _next_version(session, profile, label)
    resume = Resume(
        profile=profile,
        label=label,
        target_role=target_role,
        job_category=job_category,
        version=next_version,
        source_format=source_format,
        source_text=source_text,
        is_primary=make_primary,
    )
    session.add(resume)

    text_chunks = chunk_resume_text(source_text)
    if text_chunks:
        vectors = embed_texts([c.text for c in text_chunks])
        for order_index, (chunk, vector) in enumerate(zip(text_chunks, vectors, strict=True)):
            session.add(
                ResumeChunk(
                    resume=resume,
                    kind=chunk.kind,
                    section=chunk.section,
                    text=chunk.text,
                    order_index=order_index,
                    span_start=chunk.span_start,
                    span_end=chunk.span_end,
                    skill_ids=sorted(chunk.skill_ids),
                    embedding=encode_vector(vector),
                    embedding_model=EMBEDDING_MODEL_NAME,
                    embedding_dim=EMBEDDING_DIM,
                )
            )

    session.flush()
    return resume


def _next_version(session: Session, profile: Profile, label: str) -> int:
    stmt = select(Resume.version).where(
        Resume.profile_id == profile.id, Resume.label == label
    )
    versions = session.execute(stmt).scalars().all()
    return max(versions, default=0) + 1


def _profile_has_any_resume(session: Session, profile: Profile) -> bool:
    stmt = select(Resume.id).where(Resume.profile_id == profile.id).limit(1)
    return session.execute(stmt).first() is not None


def _clear_existing_primary(session: Session, profile: Profile) -> None:
    session.execute(
        update(Resume)
        .where(Resume.profile_id == profile.id, Resume.is_primary.is_(True))
        .values(is_primary=False)
    )


def set_primary_resume(session: Session, profile: Profile, resume_id: int) -> Resume:
    """Promote one of the profile's existing resumes to primary, demoting
    whichever one held that spot before -- the same invariant create_resume
    enforces (exactly one primary once any resume exists)."""
    resume = session.get(Resume, resume_id)
    if resume is None or resume.profile_id != profile.id:
        raise ResumeNotFoundError(resume_id)

    if not resume.is_primary:
        _clear_existing_primary(session, profile)
        resume.is_primary = True
        session.flush()
    return resume
