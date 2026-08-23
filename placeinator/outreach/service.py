"""Wires real profile/job/match data into placeinator.outreach.templates
and persists the result as an OutreachDraft.

"Cold-Mail Target Selection" (spec §6) is placeinator.jobs.service.rank_jobs
itself, reused directly rather than a second scorer -- the identical
reasoning placeinator.career.gaps applies to skill-gap prioritization.
Personalization draws on MatchResult.explanation's `projects`/`experience`
evidence: real resume bullet text the matching engine already scored, never
invented (ADR 0002).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from placeinator.db.models import Job, OutreachDraft, Profile, Resume
from placeinator.jobs.service import JobRanking, rank_jobs
from placeinator.matching.service import match_resume_to_job
from placeinator.outreach.templates import render_cold_email

_TOP_N_TARGETS = 20
# More than this starts to read as a form letter rather than a
# personalized email -- the point is a couple of specific, real claims.
_MAX_HIGHLIGHTS = 3


class OutreachDraftNotFoundError(ValueError):
    pass


def list_targets(session: Session, profile: Profile) -> list[JobRanking]:
    """Reuses the existing ranking rather than a second relevance scorer --
    JobRanking.overall_score already encodes role/location/salary/skills/
    industry/preference relevance (placeinator.jobs.filtering), which is
    exactly spec §6's Cold-Mail Target Selection criteria list. Hard-
    filtered jobs are excluded: not a real target, same reasoning as
    placeinator.career.gaps."""
    rankings = [r for r in rank_jobs(session, profile) if r.filtered_out_reason is None]
    return rankings[:_TOP_N_TARGETS]


def _top_evidence_texts(explanation: dict, *, limit: int) -> list[str]:
    """Real resume bullet text from the match's top contributing chunks.
    Only `projects`/`experience` ever carry evidence -- `overall` and
    `role` don't (placeinator.matching.scoring)."""
    texts: list[str] = []
    for component_name in ("projects", "experience"):
        component = explanation.get(component_name)
        if not component:
            continue
        for item in component.get("evidence", []):
            text = item.get("resume_text")
            if text and text not in texts:
                texts.append(text)
    return texts[:limit]


def _matched_skill_ids(explanation: dict) -> list[str]:
    skills = explanation.get("skills")
    if not skills:
        return []
    # _score_skills stores the matched skill_id as both resume_text and
    # requirement_text (they're the same taxonomy id) -- either works.
    return [item["resume_text"] for item in skills.get("evidence", [])]


def draft_email(session: Session, job: Job, resume: Resume) -> OutreachDraft:
    profile = resume.profile
    preferences = profile.preferences
    target_role = (
        preferences.target_roles[0] if preferences and preferences.target_roles else None
    )

    match_result = match_resume_to_job(session, resume, job)
    content = render_cold_email(
        full_name=profile.full_name,
        email=profile.email,
        phone=profile.phone,
        target_role=target_role,
        company=job.company,
        designation=job.designation,
        location=job.location,
        highlights=_top_evidence_texts(match_result.explanation, limit=_MAX_HIGHLIGHTS),
        matched_skills=_matched_skill_ids(match_result.explanation),
    )

    draft = session.execute(
        select(OutreachDraft).where(
            OutreachDraft.resume_id == resume.id, OutreachDraft.job_id == job.id
        )
    ).scalar_one_or_none()
    if draft is None:
        draft = OutreachDraft(resume_id=resume.id, job_id=job.id)
        session.add(draft)

    draft.subject = content.subject
    draft.body = content.body

    session.flush()
    return draft


def list_drafts(session: Session, profile: Profile) -> list[OutreachDraft]:
    stmt = (
        select(OutreachDraft)
        .join(Resume, OutreachDraft.resume_id == Resume.id)
        .where(Resume.profile_id == profile.id)
        .order_by(OutreachDraft.updated_at.desc())
    )
    return list(session.execute(stmt).scalars())


def delete_draft(session: Session, draft_id: int) -> None:
    draft = session.get(OutreachDraft, draft_id)
    if draft is None:
        raise OutreachDraftNotFoundError(f"no outreach draft with id {draft_id}")
    session.delete(draft)
    session.flush()
