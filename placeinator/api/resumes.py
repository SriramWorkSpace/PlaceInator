"""Resume library endpoints."""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from placeinator.db.models import Profile, Resume
from placeinator.db.session import get_session
from placeinator.profile.service import get_profile
from placeinator.resumes.parsing import (
    SUPPORTED_FORMATS,
    EmptyDocumentError,
    SourceFormat,
    UnsupportedFormatError,
)
from placeinator.resumes.service import (
    ResumeNotFoundError,
    create_resume,
    extract_profile_preview,
    list_resumes,
    set_primary_resume,
)

router = APIRouter(prefix="/api/resumes", tags=["resumes"])


class ResumeOut(BaseModel):
    id: int
    label: str
    target_role: str | None
    version: int
    job_category: str | None
    source_format: str
    chunk_count: int
    is_primary: bool

    model_config = {"from_attributes": True}


class ExtractedProfileOut(BaseModel):
    full_name: str | None
    email: str | None
    phone: str | None
    college: str | None
    department: str | None


def _to_out(resume: Resume) -> ResumeOut:
    return ResumeOut(
        id=resume.id,
        label=resume.label,
        target_role=resume.target_role,
        version=resume.version,
        job_category=resume.job_category,
        source_format=resume.source_format,
        chunk_count=len(resume.chunks),
        is_primary=resume.is_primary,
    )


def _require_profile(session: Session) -> Profile:
    profile = get_profile(session)
    if profile is None:
        raise HTTPException(
            status.HTTP_412_PRECONDITION_FAILED,
            "complete onboarding (PUT /api/profile) before adding resumes",
        )
    return profile


def _parse_source_format(source_format: str) -> SourceFormat:
    if source_format not in SUPPORTED_FORMATS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"source_format must be one of {SUPPORTED_FORMATS}, got {source_format!r}",
        )
    return cast(SourceFormat, source_format)


@router.get("", response_model=list[ResumeOut])
def read_resumes(session: Session = Depends(get_session)) -> list[ResumeOut]:
    profile = _require_profile(session)
    return [_to_out(r) for r in list_resumes(session, profile)]


@router.post("/extract", response_model=ExtractedProfileOut)
async def extract_profile_from_resume(
    source_format: str = Form(...),
    file: UploadFile = File(...),
) -> ExtractedProfileOut:
    """Best-effort autofill preview for onboarding: parses the uploaded resume
    and returns whatever contact/education fields it can confidently find, but
    writes nothing -- no profile needs to exist yet. The file is re-uploaded
    via POST /api/resumes once the user confirms the profile form."""
    parsed_format = _parse_source_format(source_format)

    file_bytes = await file.read()
    try:
        fields = extract_profile_preview(parsed_format, file_bytes)
    except EmptyDocumentError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except UnsupportedFormatError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    return ExtractedProfileOut(
        full_name=fields.full_name,
        email=fields.email,
        phone=fields.phone,
        college=fields.college,
        department=fields.department,
    )


@router.post("", response_model=ResumeOut, status_code=status.HTTP_201_CREATED)
async def upload_resume(
    label: str = Form(...),
    source_format: str = Form(...),
    target_role: str | None = Form(default=None),
    job_category: str | None = Form(default=None),
    is_primary: bool = Form(default=False),
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> ResumeOut:
    profile = _require_profile(session)
    parsed_format = _parse_source_format(source_format)

    file_bytes = await file.read()
    try:
        resume = create_resume(
            session,
            profile,
            label=label,
            target_role=target_role,
            job_category=job_category,
            source_format=parsed_format,
            file_bytes=file_bytes,
            is_primary=is_primary,
        )
    except EmptyDocumentError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except UnsupportedFormatError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    return _to_out(resume)


@router.patch("/{resume_id}/primary", response_model=ResumeOut)
def make_primary(resume_id: int, session: Session = Depends(get_session)) -> ResumeOut:
    profile = _require_profile(session)
    try:
        resume = set_primary_resume(session, profile, resume_id)
    except ResumeNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no resume with id {resume_id}") from exc
    return _to_out(resume)
