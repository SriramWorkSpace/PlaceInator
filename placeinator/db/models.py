"""ORM schema.

Single-user application: exactly one Profile row exists, so child tables link to
it directly rather than carrying a tenant key.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from placeinator.db.base import Base, TimestampMixin
from placeinator.db.enums import (
    ChunkKind,
    EventType,
    JobType,
    PlacementStatus,
    RequirementKind,
    SourceKind,
    WorkMode,
)
from placeinator.db.types import enum_column

# --------------------------------------------------------------------------- #
# Profile and preferences (spec section 1)
# --------------------------------------------------------------------------- #


class Profile(Base, TimestampMixin):
    __tablename__ = "profile"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(40))
    college: Mapped[str | None] = mapped_column(String(200))
    department: Mapped[str | None] = mapped_column(String(200))
    student_id: Mapped[str | None] = mapped_column(String(64))

    # Alternate spellings used for candidate identification in placement sheets,
    # where the same person appears as "S. Madala", "Sriram M", and so on.
    name_aliases: Mapped[list[str]] = mapped_column(JSON, default=list)

    onboarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    preferences: Mapped[Preferences | None] = relationship(
        back_populates="profile", uselist=False, cascade="all, delete-orphan"
    )
    resumes: Mapped[list[Resume]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )


class Preferences(Base, TimestampMixin):
    """Career preferences and employment constraints (spec lines 34-51)."""

    __tablename__ = "preferences"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profile.id", ondelete="CASCADE"))

    target_roles: Mapped[list[str]] = mapped_column(JSON, default=list)
    preferred_industries: Mapped[list[str]] = mapped_column(JSON, default=list)
    preferred_locations: Mapped[list[str]] = mapped_column(JSON, default=list)
    work_mode: Mapped[WorkMode] = mapped_column(enum_column(WorkMode), default=WorkMode.ANY)

    # Hard constraint: a job below this is eliminated, not merely down-ranked.
    min_salary: Mapped[float | None] = mapped_column(Float)
    preferred_salary_min: Mapped[float | None] = mapped_column(Float)
    preferred_salary_max: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="INR")

    willing_to_relocate: Mapped[bool] = mapped_column(default=True)
    target_experience_years: Mapped[float | None] = mapped_column(Float)

    accepts_fixed_term: Mapped[bool] = mapped_column(default=True)
    max_contract_months: Mapped[int | None] = mapped_column(Integer)
    accepts_service_bond: Mapped[bool] = mapped_column(default=True)
    max_bond_months: Mapped[int | None] = mapped_column(Integer)
    other_restrictions: Mapped[str | None] = mapped_column(Text)

    profile: Mapped[Profile] = relationship(back_populates="preferences")


# --------------------------------------------------------------------------- #
# Resume library (spec section 3)
# --------------------------------------------------------------------------- #


class Resume(Base, TimestampMixin):
    __tablename__ = "resume"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profile.id", ondelete="CASCADE"))

    label: Mapped[str] = mapped_column(String(120))
    target_role: Mapped[str | None] = mapped_column(String(160))
    version: Mapped[int] = mapped_column(Integer, default=1)
    job_category: Mapped[str | None] = mapped_column(String(120))

    source_format: Mapped[str] = mapped_column(String(16))  # pdf | docx | tex
    source_path: Mapped[str | None] = mapped_column(Text)
    # LaTeX tailoring splices byte ranges out of this exact text, so it is the
    # authoritative copy -- never re-derive it from the file on disk.
    source_text: Mapped[str] = mapped_column(Text)

    profile: Mapped[Profile] = relationship(back_populates="resumes")
    chunks: Mapped[list[ResumeChunk]] = relationship(
        back_populates="resume", cascade="all, delete-orphan"
    )
    matches: Mapped[list[MatchResult]] = relationship(
        back_populates="resume", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("profile_id", "label", "version"),)


class ResumeChunk(Base):
    """A scorable unit of a resume, tied back to its span in Resume.source_text."""

    __tablename__ = "resume_chunk"

    id: Mapped[int] = mapped_column(primary_key=True)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resume.id", ondelete="CASCADE"))

    kind: Mapped[ChunkKind] = mapped_column(enum_column(ChunkKind))
    section: Mapped[str | None] = mapped_column(String(120))
    text: Mapped[str] = mapped_column(Text)
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    # Character offsets into source_text; the splice emitter depends on these.
    span_start: Mapped[int | None] = mapped_column(Integer)
    span_end: Mapped[int | None] = mapped_column(Integer)

    # Normalized taxonomy ids recognised in this chunk.
    skill_ids: Mapped[list[str]] = mapped_column(JSON, default=list)

    # float32 little-endian, C-contiguous, L2-normalized. Always write via
    # placeinator.matching.vectors so the encoding stays in exactly one place.
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary)
    embedding_model: Mapped[str | None] = mapped_column(String(96))
    embedding_dim: Mapped[int | None] = mapped_column(Integer)

    resume: Mapped[Resume] = relationship(back_populates="chunks")

    __table_args__ = (Index("ix_resume_chunk_resume_kind", "resume_id", "kind"),)


# --------------------------------------------------------------------------- #
# Jobs (spec section 2)
# --------------------------------------------------------------------------- #


class Job(Base, TimestampMixin):
    __tablename__ = "job"

    id: Mapped[int] = mapped_column(primary_key=True)

    source: Mapped[SourceKind] = mapped_column(enum_column(SourceKind), default=SourceKind.MANUAL)
    # Stable per-source id; lets a rescan update rather than duplicate.
    source_ref: Mapped[str | None] = mapped_column(String(255))
    url: Mapped[str | None] = mapped_column(Text)

    company: Mapped[str] = mapped_column(String(200))
    designation: Mapped[str] = mapped_column(String(200))
    location: Mapped[str | None] = mapped_column(String(200))
    work_mode: Mapped[WorkMode] = mapped_column(enum_column(WorkMode), default=WorkMode.ANY)
    job_type: Mapped[JobType] = mapped_column(enum_column(JobType), default=JobType.UNKNOWN)

    salary_min: Mapped[float | None] = mapped_column(Float)
    salary_max: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str | None] = mapped_column(String(8))

    experience_min_years: Mapped[float | None] = mapped_column(Float)
    experience_max_years: Mapped[float | None] = mapped_column(Float)

    bond_months: Mapped[int | None] = mapped_column(Integer)
    contract_months: Mapped[int | None] = mapped_column(Integer)

    education_requirements: Mapped[list[str]] = mapped_column(JSON, default=list)
    required_skill_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    preferred_skill_ids: Mapped[list[str]] = mapped_column(JSON, default=list)

    deadline: Mapped[date | None] = mapped_column(Date)
    description: Mapped[str] = mapped_column(Text)

    # Result of hard-constraint filtering. A rejected job is kept, not deleted,
    # so the UI can explain why it was excluded.
    filtered_out_reason: Mapped[str | None] = mapped_column(Text)

    requirements: Mapped[list[JobRequirement]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    matches: Mapped[list[MatchResult]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("source", "source_ref", name="uq_job_source_ref"),
        Index("ix_job_company_designation", "company", "designation"),
    )


class JobRequirement(Base):
    """A scorable line extracted from a job description."""

    __tablename__ = "job_requirement"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job.id", ondelete="CASCADE"))

    kind: Mapped[RequirementKind] = mapped_column(enum_column(RequirementKind))
    text: Mapped[str] = mapped_column(Text)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    skill_ids: Mapped[list[str]] = mapped_column(JSON, default=list)

    # See ResumeChunk.embedding for the encoding contract.
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary)
    embedding_model: Mapped[str | None] = mapped_column(String(96))
    embedding_dim: Mapped[int | None] = mapped_column(Integer)

    job: Mapped[Job] = relationship(back_populates="requirements")

    __table_args__ = (Index("ix_job_requirement_job_kind", "job_id", "kind"),)


# --------------------------------------------------------------------------- #
# Matching (spec sections 2 and 3)
# --------------------------------------------------------------------------- #


class MatchResult(Base, TimestampMixin):
    """One (resume, job) score, with the evidence that produced it.

    The explanation column is the single record behind three spec features:
    notification reasons, resume recommendation, and the tailoring change log.
    """

    __tablename__ = "match_result"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("job.id", ondelete="CASCADE"))
    resume_id: Mapped[int] = mapped_column(ForeignKey("resume.id", ondelete="CASCADE"))

    semantic_score: Mapped[float] = mapped_column(Float, default=0.0)
    personalized_score: Mapped[float] = mapped_column(Float, default=0.0)

    # {component: {"value": float, "weight": float, "evidence": [...]}}
    explanation: Mapped[dict] = mapped_column(JSON, default=dict)

    # Version of the weights and model used, so stale scores are detectable.
    scoring_version: Mapped[str] = mapped_column(String(32), default="")

    job: Mapped[Job] = relationship(back_populates="matches")
    resume: Mapped[Resume] = relationship(back_populates="matches")

    __table_args__ = (
        UniqueConstraint("job_id", "resume_id", name="uq_match_job_resume"),
        Index("ix_match_personalized_score", "personalized_score"),
    )


# --------------------------------------------------------------------------- #
# Placement automation (spec section 7)
# --------------------------------------------------------------------------- #


class PlacementRecord(Base, TimestampMixin):
    """A detected appearance of the user in a placement communication."""

    __tablename__ = "placement_record"

    id: Mapped[int] = mapped_column(primary_key=True)

    gmail_message_id: Mapped[str] = mapped_column(String(128))
    company: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[PlacementStatus] = mapped_column(
        enum_column(PlacementStatus), default=PlacementStatus.UNKNOWN
    )

    # Below the auto-accept threshold the record waits in the review queue
    # rather than the pipeline acting on a guess.
    match_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    needs_review: Mapped[bool] = mapped_column(default=True)

    matched_on: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_document: Mapped[str | None] = mapped_column(Text)
    raw_row: Mapped[dict] = mapped_column(JSON, default=dict)

    events: Mapped[list[PlacementEvent]] = relationship(
        back_populates="record", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_placement_record_message", "gmail_message_id"),)


class PlacementEvent(Base, TimestampMixin):
    __tablename__ = "placement_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    record_id: Mapped[int | None] = mapped_column(
        ForeignKey("placement_record.id", ondelete="CASCADE")
    )

    company: Mapped[str] = mapped_column(String(200))
    event_type: Mapped[EventType] = mapped_column(enum_column(EventType), default=EventType.OTHER)
    round_name: Mapped[str | None] = mapped_column(String(120))

    event_date: Mapped[date | None] = mapped_column(Date)
    start_time: Mapped[str | None] = mapped_column(String(16))
    end_time: Mapped[str | None] = mapped_column(String(16))
    reporting_time: Mapped[str | None] = mapped_column(String(16))
    venue: Mapped[str | None] = mapped_column(Text)
    meeting_link: Mapped[str | None] = mapped_column(Text)
    instructions: Mapped[str | None] = mapped_column(Text)

    # sha256(company, event_type, date, start_time) -- the duplicate guard.
    dedupe_key: Mapped[str] = mapped_column(String(64))
    calendar_event_id: Mapped[str | None] = mapped_column(String(255))
    extraction_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    needs_review: Mapped[bool] = mapped_column(default=True)

    record: Mapped[PlacementRecord | None] = relationship(back_populates="events")

    __table_args__ = (UniqueConstraint("dedupe_key", name="uq_placement_event_dedupe"),)
