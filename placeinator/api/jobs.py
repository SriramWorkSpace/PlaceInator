"""Job intake endpoints. Adapter-based discovery (Indeed, ATS feeds, ...) lands
in M2; only manual paste exists here -- see ADR 0003 on why manual is never
optional regardless of what else ships."""

from __future__ import annotations

from datetime import date
from typing import Literal, cast

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from placeinator.db.enums import SourceKind
from placeinator.db.models import Job, Profile
from placeinator.db.session import get_session
from placeinator.jobs.extraction import extract_job_fields
from placeinator.jobs.parsing import (
    SUPPORTED_JD_FORMATS,
    EmptyJdDocumentError,
    JdSourceFormat,
    UnsupportedJdFormatError,
    parse_jd_bytes,
)
from placeinator.jobs.service import (
    JobNotFoundError,
    JobRanking,
    create_manual_job,
    list_jobs,
    list_notifications,
    mark_notification_seen,
    rank_jobs,
    search_jobs,
    sync_ats_feed,
)
from placeinator.jobs.sources.base import SearchQuery, SourceBlocked
from placeinator.profile.service import get_profile

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _require_profile(session: Session) -> Profile:
    profile = get_profile(session)
    if profile is None:
        raise HTTPException(status.HTTP_412_PRECONDITION_FAILED, "complete onboarding first")
    return profile


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
    # Hard-constraint verdict (spec §2) -- never hidden when set, since a
    # filtered job is kept, not deleted, so the UI can explain the exclusion.
    filtered_out_reason: str | None

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
        filtered_out_reason=job.filtered_out_reason,
    )


class JobRankingOut(BaseModel):
    job: JobOut
    # None when there's no primary resume to score against.
    semantic_score: float | None
    soft_preference_score: float
    soft_preference_reasons: list[str]
    overall_score: float


def _to_ranking_out(ranking: JobRanking) -> JobRankingOut:
    return JobRankingOut(
        job=_to_out(ranking.job),
        semantic_score=ranking.semantic_score,
        soft_preference_score=ranking.soft_preference_score,
        soft_preference_reasons=ranking.soft_preference_reasons,
        overall_score=ranking.overall_score,
    )


class ExtractedJobOut(BaseModel):
    designation: str | None
    company: str | None
    # The full parsed text -- this is what actually prefills the description
    # field and drives matching; designation/company are just a convenience
    # on top, and are frequently null since a JD's layout is far less
    # standardized than a resume's header block.
    description: str


@router.get("", response_model=list[JobOut])
def read_jobs(session: Session = Depends(get_session)) -> list[JobOut]:
    return [_to_out(j) for j in list_jobs(session)]


@router.get("/ranked", response_model=list[JobRankingOut])
def read_ranked_jobs(session: Session = Depends(get_session)) -> list[JobRankingOut]:
    """The Jobs UI's ranked list (spec §2): best first, hard-filtered jobs
    kept but sorted last with their reason attached, never hidden."""
    profile = _require_profile(session)
    return [_to_ranking_out(r) for r in rank_jobs(session, profile)]


@router.get("/notifications", response_model=list[JobRankingOut])
def read_notifications(session: Session = Depends(get_session)) -> list[JobRankingOut]:
    """Jobs worth interrupting the user for (spec §2's Personalized Job
    Notifications): passes hard filters, scores above NOTIFICATION_THRESHOLD,
    and hasn't been marked seen yet."""
    profile = _require_profile(session)
    return [_to_ranking_out(r) for r in list_notifications(session, profile)]


@router.post("/{job_id}/notifications/seen", response_model=JobOut)
def notification_seen(job_id: int, session: Session = Depends(get_session)) -> JobOut:
    try:
        job = mark_notification_seen(session, job_id)
    except JobNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no job with id {job_id}") from exc
    return _to_out(job)


@router.post("/extract", response_model=ExtractedJobOut)
async def extract_job_from_file(
    source_format: str = Form(...),
    file: UploadFile = File(...),
) -> ExtractedJobOut:
    """Parses an uploaded JD (PDF/DOCX) for the manual-add form -- writes
    nothing. The extracted text is submitted back through POST /api/jobs/manual
    once the user reviews and confirms the form."""
    if source_format not in SUPPORTED_JD_FORMATS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"source_format must be one of {SUPPORTED_JD_FORMATS}, got {source_format!r}",
        )
    parsed_format = cast(JdSourceFormat, source_format)

    file_bytes = await file.read()
    try:
        text = parse_jd_bytes(file_bytes, parsed_format)
    except EmptyJdDocumentError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except UnsupportedJdFormatError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    fields = extract_job_fields(text)
    return ExtractedJobOut(designation=fields.designation, company=fields.company, description=text)


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


class JobSearchIn(BaseModel):
    source: Literal["indeed", "linkedin", "naukri"]
    keywords: str = ""
    location: str | None = None


class JobSearchOut(BaseModel):
    jobs: list[JobOut]
    # Present, and jobs empty, when ADR 0003's boundary was hit -- expected
    # and common for linkedin/naukri, not exceptional. The UI's response is
    # to offer manual paste, not to show an error.
    blocked_reason: str | None = None


@router.post("/search", response_model=JobSearchOut)
def search_jobs_endpoint(
    data: JobSearchIn, session: Session = Depends(get_session)
) -> JobSearchOut:
    query = SearchQuery(keywords=data.keywords, location=data.location)
    result = search_jobs(session, SourceKind(data.source), query)
    if isinstance(result, SourceBlocked):
        return JobSearchOut(jobs=[], blocked_reason=result.reason)
    return JobSearchOut(jobs=[_to_out(job) for job in result])
