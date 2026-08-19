"""Resume recommendation: rank every resume in the library against one job.

This is the M1 acceptance path end to end: add resumes, paste a JD via
POST /api/jobs/manual, then call this endpoint to get a ranked list with an
explanation per resume (spec §3's "Recommended: SDE Resume" flow).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from placeinator.db.models import Job, MatchResult
from placeinator.db.session import get_session
from placeinator.matching.service import rank_resumes_for_job
from placeinator.profile.service import get_profile

router = APIRouter(prefix="/api/matching", tags=["matching"])


class MatchOut(BaseModel):
    resume_id: int
    resume_label: str
    semantic_score: float
    personalized_score: float
    explanation: dict

    model_config = {"from_attributes": True}


def _to_out(result: MatchResult) -> MatchOut:
    return MatchOut(
        resume_id=result.resume_id,
        # Loaded via the relationship rather than a join, since the resume
        # list here is always small (a personal resume library, not a corpus).
        resume_label=result.resume.label,
        semantic_score=result.semantic_score,
        personalized_score=result.personalized_score,
        explanation=result.explanation,
    )


@router.post("/jobs/{job_id}/rank-resumes", response_model=list[MatchOut])
def rank_resumes(job_id: int, session: Session = Depends(get_session)) -> list[MatchOut]:
    profile = get_profile(session)
    if profile is None:
        raise HTTPException(status.HTTP_412_PRECONDITION_FAILED, "complete onboarding first")

    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no job with id {job_id}")

    if not profile.resumes:
        raise HTTPException(
            status.HTTP_412_PRECONDITION_FAILED, "upload at least one resume first"
        )

    results = rank_resumes_for_job(session, profile, job)
    return [_to_out(r) for r in results]
