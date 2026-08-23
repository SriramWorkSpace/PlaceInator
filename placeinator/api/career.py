"""Career skill intelligence endpoints (specification section 4)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from placeinator.career.gaps import SkillGap, analyze_skill_gaps
from placeinator.career.resources import get_resource_library
from placeinator.db.session import get_session
from placeinator.profile.service import get_profile

router = APIRouter(prefix="/api/career", tags=["career"])


class GapEvidenceOut(BaseModel):
    job_id: int
    company: str
    designation: str
    required: bool


class ResourceOut(BaseModel):
    title: str
    url: str


class SkillGapOut(BaseModel):
    skill_id: str
    priority: float
    evidence: list[GapEvidenceOut]
    # None when no verified resource exists for this skill yet -- never a
    # fabricated one (placeinator.career.resources' own contract).
    resource: ResourceOut | None


def _to_out(gap: SkillGap) -> SkillGapOut:
    resource = get_resource_library().get(gap.skill_id)
    return SkillGapOut(
        skill_id=gap.skill_id,
        priority=gap.priority,
        evidence=[
            GapEvidenceOut(
                job_id=e.job_id, company=e.company, designation=e.designation, required=e.required
            )
            for e in gap.evidence
        ],
        resource=ResourceOut(title=resource.title, url=resource.url) if resource else None,
    )


@router.get("/skill-gaps", response_model=list[SkillGapOut])
def read_skill_gaps(session: Session = Depends(get_session)) -> list[SkillGapOut]:
    profile = get_profile(session)
    if profile is None:
        raise HTTPException(status.HTTP_412_PRECONDITION_FAILED, "complete onboarding first")
    return [_to_out(gap) for gap in analyze_skill_gaps(session, profile)]
