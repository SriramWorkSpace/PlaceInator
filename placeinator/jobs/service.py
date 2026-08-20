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

from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from placeinator.db.enums import RequirementKind, SourceKind
from placeinator.db.models import Job, JobRequirement, Preferences, Profile
from placeinator.jobs.filtering import (
    SEMANTIC_MATCH_WEIGHT,
    SOFT_PREFERENCE_WEIGHT,
    apply_hard_filters,
    score_soft_preferences,
)
from placeinator.jobs.sources.ats_feed import AtsFeedSource
from placeinator.jobs.sources.base import JobSource, RawPosting, SearchQuery, SourceBlocked
from placeinator.jobs.sources.indeed import IndeedSource
from placeinator.jobs.sources.linkedin import LinkedInSource
from placeinator.jobs.sources.naukri import NaukriSource
from placeinator.matching.chunking import chunk_job_description
from placeinator.matching.service import match_resume_to_job
from placeinator.matching.vectors import (
    EMBEDDING_DIM,
    EMBEDDING_MODEL_NAME,
    embed_texts,
    encode_vector,
)


class JobNotFoundError(ValueError):
    pass


# Fallback minimum overall_score for a job to surface as a personalized
# notification (spec §2: "opportunities that meet their preferences and
# match threshold"), used only if a profile somehow has no Preferences row
# yet -- the real, user-adjustable value lives at
# Preferences.notification_threshold (Settings page). Deliberately separate
# from ranking, which shows every non-filtered job regardless of score --
# notifications are the subset worth interrupting the user for.
NOTIFICATION_THRESHOLD = 0.6


@dataclass(frozen=True)
class JobRanking:
    """One job's place in the personalized ranking (spec §2's Personalized Job
    Ranking): the hard-filter verdict plus the semantic and soft-preference
    signals that combine into overall_score, each kept separate so the UI can
    show *why* a job ranked where it did rather than just the number."""

    job: Job
    filtered_out_reason: str | None
    # None when there is no primary resume to score against -- soft
    # preferences and hard filters still apply, only the semantic half of
    # the ranking is unavailable.
    semantic_score: float | None
    soft_preference_score: float
    soft_preference_reasons: list[str] = field(default_factory=list)

    @property
    def overall_score(self) -> float:
        if self.filtered_out_reason is not None:
            return 0.0
        if self.semantic_score is None:
            return self.soft_preference_score
        return (
            SEMANTIC_MATCH_WEIGHT * self.semantic_score
            + SOFT_PREFERENCE_WEIGHT * self.soft_preference_score
        )


def list_jobs(session: Session) -> list[Job]:
    stmt = select(Job).order_by(Job.created_at.desc())
    return list(session.execute(stmt).scalars())


def _current_preferences(session: Session) -> Preferences | None:
    # Single-user application (placeinator.profile.service.get_profile is the
    # same idiom): exactly one Profile row, so there is no id to look up by.
    profile = session.execute(select(Profile).limit(1)).scalar_one_or_none()
    return profile.preferences if profile else None


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
    job.filtered_out_reason = apply_hard_filters(job, _current_preferences(session))
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
    job.filtered_out_reason = apply_hard_filters(job, _current_preferences(session))
    session.flush()
    return job


def refilter_jobs(session: Session, preferences: Preferences | None) -> None:
    """Re-evaluates hard constraints against every existing job -- called
    whenever preferences change (placeinator.profile.service.upsert_profile),
    so Job.filtered_out_reason never goes stale after a save."""
    for job in list_jobs(session):
        job.filtered_out_reason = apply_hard_filters(job, preferences)


def rank_jobs(session: Session, profile: Profile) -> list[JobRanking]:
    """The Jobs UI's ranked list (spec §2's Personalized Job Ranking):
    combines the semantic match against the profile's primary resume with
    the soft-preference signal, sorted best first. Filtered-out jobs are
    never hidden -- they sort last, with the reason attached, per
    Job.filtered_out_reason's own contract ("kept, not deleted").
    """
    preferences = profile.preferences
    primary_resume = next((r for r in profile.resumes if r.is_primary), None)

    rankings = []
    for job in list_jobs(session):
        soft = score_soft_preferences(job, preferences)
        semantic_score = None
        if primary_resume is not None and job.filtered_out_reason is None:
            match_result = match_resume_to_job(session, primary_resume, job)
            semantic_score = match_result.personalized_score

        rankings.append(
            JobRanking(
                job=job,
                filtered_out_reason=job.filtered_out_reason,
                semantic_score=semantic_score,
                soft_preference_score=soft.value,
                soft_preference_reasons=soft.reasons,
            )
        )

    rankings.sort(key=lambda r: (r.filtered_out_reason is not None, -r.overall_score))
    return rankings


def _qualifies_for_notification(ranking: JobRanking, threshold: float) -> bool:
    return (
        ranking.filtered_out_reason is None
        and ranking.semantic_score is not None
        and ranking.overall_score >= threshold
    )


def list_notifications(session: Session, profile: Profile) -> list[JobRanking]:
    """Jobs that qualify as a personalized notification (spec §2) and haven't
    been marked seen yet: passes hard filters, has a semantic score against
    the primary resume (no primary resume means no notifications -- there is
    nothing to say "this matches you" about), and clears the user's
    notification_threshold (Settings page; falls back to
    NOTIFICATION_THRESHOLD if preferences somehow don't exist yet). Sorted
    the same as rank_jobs, best first.
    """
    threshold = (
        profile.preferences.notification_threshold
        if profile.preferences is not None
        else NOTIFICATION_THRESHOLD
    )
    return [
        r
        for r in rank_jobs(session, profile)
        if _qualifies_for_notification(r, threshold) and r.job.notification_seen_at is None
    ]


def mark_notification_seen(session: Session, job_id: int) -> Job:
    job = session.get(Job, job_id)
    if job is None:
        raise JobNotFoundError(job_id)
    if job.notification_seen_at is None:
        job.notification_seen_at = datetime.now(UTC)
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


# indeed/linkedin/naukri all take the same free-text keywords+location shape
# (SearchQuery), unlike ats_feed's company-slug list -- one dispatch table
# and one function covers all three, rather than three near-duplicates of
# sync_ats_feed's shape.
_SEARCH_SOURCES: dict[SourceKind, type[JobSource]] = {
    SourceKind.INDEED: IndeedSource,
    SourceKind.LINKEDIN: LinkedInSource,
    SourceKind.NAUKRI: NaukriSource,
}


def search_jobs(
    session: Session, source: SourceKind, query: SearchQuery
) -> list[Job] | SourceBlocked:
    """Keyword/location search against indeed/linkedin/naukri (ADR 0003).
    ``SourceBlocked`` is the expected, common outcome for linkedin/naukri --
    see their adapters' module docstrings for why -- and is never treated as
    an error here, only reported."""
    adapter_cls = _SEARCH_SOURCES[source]
    with adapter_cls() as adapter:
        result = adapter.fetch(query)

    if isinstance(result, SourceBlocked):
        return result

    return [upsert_job_from_posting(session, source, posting) for posting in result]


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
