"""Resume persistence: parse, chunk, embed, store.

Every chunk is embedded and stamped with its provenance (embedding_model,
embedding_dim) per the encoding contract in placeinator.matching.vectors, so a
future model change leaves stale rows detectable rather than silently wrong.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from placeinator.db.models import Profile, Resume, ResumeChunk
from placeinator.matching.chunking import chunk_resume_text
from placeinator.matching.vectors import (
    EMBEDDING_DIM,
    EMBEDDING_MODEL_NAME,
    embed_texts,
    encode_vector,
)
from placeinator.resumes.parsing import SourceFormat, parse_resume_bytes


def list_resumes(session: Session, profile: Profile) -> list[Resume]:
    stmt = select(Resume).where(Resume.profile_id == profile.id).order_by(Resume.label)
    return list(session.execute(stmt).scalars())


def create_resume(
    session: Session,
    profile: Profile,
    *,
    label: str,
    target_role: str | None,
    job_category: str | None,
    source_format: SourceFormat,
    file_bytes: bytes,
) -> Resume:
    """Parse an uploaded file, chunk it, embed every chunk, and persist all of
    it as one Resume with its ResumeChunk children.

    Versioning follows spec §3 ("Each resume can have ... Version"): a resume
    is identified by (profile, label); re-uploading the same label creates the
    next version rather than overwriting history.
    """
    source_text = parse_resume_bytes(file_bytes, source_format)

    next_version = _next_version(session, profile, label)
    resume = Resume(
        profile=profile,
        label=label,
        target_role=target_role,
        job_category=job_category,
        version=next_version,
        source_format=source_format,
        source_text=source_text,
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
