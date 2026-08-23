"""Skill-gap analysis (spec §4): aggregates required/preferred skills across
the user's ranked target jobs, subtracts skills they already have, and
prioritizes the gaps -- reusing `placeinator.jobs.service.rank_jobs`
directly rather than a second relevance scorer. A skill that keeps
appearing in highly-ranked jobs naturally outscores one appearing only in
marginal matches, because `JobRanking.overall_score` already encodes role/
location/salary/preference relevance (`placeinator.jobs.filtering`) -- this
*is* spec's "frequency × role relevance" (§4's Skill Prioritization
subsection), without inventing a second metric.

Hard-filtered-out jobs are excluded entirely: a job the user can't actually
take (bond terms, salary floor, ...) isn't a real target, so its skill
requirements shouldn't count toward what to learn next.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from placeinator.db.models import Profile
from placeinator.jobs.service import JobRanking, rank_jobs

# A preferred-but-not-required skill still matters, but less than one a job
# outright requires -- the user could still land the role without it.
_PREFERRED_SKILL_WEIGHT = 0.5


@dataclass(frozen=True)
class GapEvidence:
    job_id: int
    company: str
    designation: str
    required: bool  # True: from required_skill_ids. False: preferred_skill_ids.


@dataclass(frozen=True)
class SkillGap:
    skill_id: str
    priority: float
    evidence: tuple[GapEvidence, ...]


def _resume_skill_ids(profile: Profile) -> set[str]:
    """The union across the whole resume library, not just the primary --
    a skill demonstrated on any resume counts as one the user has, since
    the gap is about what to *learn*, not which single resume to use."""
    skill_ids: set[str] = set()
    for resume in profile.resumes:
        for chunk in resume.chunks:
            skill_ids |= set(chunk.skill_ids)
    return skill_ids


def analyze_skill_gaps(session: Session, profile: Profile) -> list[SkillGap]:
    """The real entry point: fetches the ranking from the DB, then hands off
    to the pure aggregation below. Split this way so the prioritization
    logic itself -- the part actually worth unit-testing -- never needs a
    session, mirroring how JobRanking.overall_score is tested directly with
    hand-built rankings in tests/unit/test_jobs_ranking.py."""
    known_skills = _resume_skill_ids(profile)
    rankings = [r for r in rank_jobs(session, profile) if r.filtered_out_reason is None]
    return aggregate_skill_gaps(rankings, known_skills)


def aggregate_skill_gaps(rankings: list[JobRanking], known_skills: set[str]) -> list[SkillGap]:
    priorities: dict[str, float] = {}
    evidence: dict[str, list[GapEvidence]] = {}

    for ranking in rankings:
        job = ranking.job
        for skill_id in job.required_skill_ids:
            if skill_id in known_skills:
                continue
            priorities[skill_id] = priorities.get(skill_id, 0.0) + ranking.overall_score
            evidence.setdefault(skill_id, []).append(
                GapEvidence(
                    job_id=job.id, company=job.company, designation=job.designation, required=True
                )
            )
        for skill_id in job.preferred_skill_ids:
            if skill_id in known_skills or skill_id in job.required_skill_ids:
                continue  # already counted as required for this job above
            priorities[skill_id] = (
                priorities.get(skill_id, 0.0) + ranking.overall_score * _PREFERRED_SKILL_WEIGHT
            )
            evidence.setdefault(skill_id, []).append(
                GapEvidence(
                    job_id=job.id, company=job.company, designation=job.designation, required=False
                )
            )

    gaps = [
        SkillGap(skill_id=skill_id, priority=priority, evidence=tuple(evidence[skill_id]))
        for skill_id, priority in priorities.items()
    ]
    gaps.sort(key=lambda g: g.priority, reverse=True)
    return gaps
