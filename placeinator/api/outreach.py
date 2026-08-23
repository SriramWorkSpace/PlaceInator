"""Personalized cold-outreach endpoints (specification section 6)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from placeinator.db.models import Job, Resume
from placeinator.db.session import get_session
from placeinator.jobs.service import JobRanking
from placeinator.outreach.service import (
    OutreachDraftNotFoundError,
    delete_draft,
    draft_email,
    list_drafts,
    list_targets,
)
from placeinator.profile.service import get_profile

router = APIRouter(prefix="/api/outreach", tags=["outreach"])


class OutreachTargetJobOut(BaseModel):
    """Just enough to show and pick a target -- not the full job detail
    api/jobs.py's JobOut carries (skill ids, deadline, url, ...), none of
    which this list needs."""

    id: int
    company: str
    designation: str
    location: str | None


class OutreachTargetOut(BaseModel):
    job: OutreachTargetJobOut
    overall_score: float


def _to_target_out(ranking: JobRanking) -> OutreachTargetOut:
    job = ranking.job
    return OutreachTargetOut(
        job=OutreachTargetJobOut(
            id=job.id, company=job.company, designation=job.designation, location=job.location
        ),
        overall_score=ranking.overall_score,
    )


class DraftIn(BaseModel):
    resume_id: int
    job_id: int


class OutreachDraftOut(BaseModel):
    id: int
    resume_id: int
    job_id: int
    subject: str
    body: str

    model_config = {"from_attributes": True}


def _require_profile(session: Session):
    profile = get_profile(session)
    if profile is None:
        raise HTTPException(status.HTTP_412_PRECONDITION_FAILED, "complete onboarding first")
    return profile


@router.get("/targets", response_model=list[OutreachTargetOut])
def read_targets(session: Session = Depends(get_session)) -> list[OutreachTargetOut]:
    profile = _require_profile(session)
    return [_to_target_out(r) for r in list_targets(session, profile)]


@router.get("/drafts", response_model=list[OutreachDraftOut])
def read_drafts(session: Session = Depends(get_session)) -> list[OutreachDraftOut]:
    profile = _require_profile(session)
    return [OutreachDraftOut.model_validate(d) for d in list_drafts(session, profile)]


@router.post("/drafts", response_model=OutreachDraftOut)
def create_draft(data: DraftIn, session: Session = Depends(get_session)) -> OutreachDraftOut:
    resume = session.get(Resume, data.resume_id)
    if resume is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no resume with id {data.resume_id}")

    job = session.get(Job, data.job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no job with id {data.job_id}")

    draft = draft_email(session, job, resume)
    return OutreachDraftOut.model_validate(draft)


@router.delete("/drafts/{draft_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_draft(draft_id: int, session: Session = Depends(get_session)) -> None:
    try:
        delete_draft(session, draft_id)
    except OutreachDraftNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
