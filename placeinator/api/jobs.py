"""Job intake endpoints. Adapter-based discovery (Indeed, ATS feeds, ...) lands
in M2; only manual paste exists here -- see ADR 0003 on why manual is never
optional regardless of what else ships."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from placeinator.db.models import Job
from placeinator.db.session import get_session
from placeinator.jobs.service import create_manual_job, list_jobs, sync_ats_feed
from placeinator.jobs.sources.base import SourceBlocked

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class ManualJobIn(BaseModel):
    company: str = Field(min_length=1, max_length=200)
    designation: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
    location: str | None = None
    url: str | None = None
    deadline: date | None = None


class JobOut(BaseModel):
    id: int
    source: str
    company: str
    designation: str
    location: str | None
    deadline: date | None
    required_skill_ids: list[str]
    preferred_skill_ids: list[str]

    model_config = {"from_attributes": True}


def _to_out(job: Job) -> JobOut:
    return JobOut(
        id=job.id,
        source=job.source,
        company=job.company,
        designation=job.designation,
        location=job.location,
        deadline=job.deadline,
        required_skill_ids=job.required_skill_ids,
        preferred_skill_ids=job.preferred_skill_ids,
    )


@router.get("", response_model=list[JobOut])
def read_jobs(session: Session = Depends(get_session)) -> list[JobOut]:
    return [_to_out(j) for j in list_jobs(session)]


@router.post("/manual", response_model=JobOut, status_code=status.HTTP_201_CREATED)
def add_manual_job(data: ManualJobIn, session: Session = Depends(get_session)) -> JobOut:
    job = create_manual_job(
        session,
        company=data.company,
        designation=data.designation,
        description=data.description,
        location=data.location,
        url=data.url,
        deadline=data.deadline,
    )
    return _to_out(job)


class AtsFeedIn(BaseModel):
    # "platform:company-slug", e.g. "greenhouse:stripe" -- validated against
    # the same three platforms placeinator.jobs.sources.ats_feed supports,
    # so a typo 404s here with a clear message rather than deep inside a
    # scrape.
    companies: list[str] = Field(min_length=1)

    @staticmethod
    def _valid_entry(entry: str) -> bool:
        platform, _, slug = entry.partition(":")
        return platform in ("greenhouse", "lever", "ashby") and bool(slug)


class AtsFeedOut(BaseModel):
    jobs: list[JobOut]
    # Present, and jobs empty, when ADR 0003's boundary was hit -- the UI's
    # response is to offer manual paste, not to show an error.
    blocked_reason: str | None = None


@router.post("/ats-feed", response_model=AtsFeedOut)
def add_ats_feed_jobs(data: AtsFeedIn, session: Session = Depends(get_session)) -> AtsFeedOut:
    invalid = [e for e in data.companies if not AtsFeedIn._valid_entry(e)]
    if invalid:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"expected 'platform:company-slug' (greenhouse/lever/ashby), got: {invalid}",
        )

    result = sync_ats_feed(session, data.companies)
    if isinstance(result, SourceBlocked):
        return AtsFeedOut(jobs=[], blocked_reason=result.reason)
    return AtsFeedOut(jobs=[_to_out(job) for job in result])
