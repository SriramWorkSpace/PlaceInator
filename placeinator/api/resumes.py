"""Resume library endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from placeinator.db.models import Profile, Resume
from placeinator.db.session import get_session
from placeinator.profile.service import get_profile
from placeinator.resumes.parsing import (
    SUPPORTED_FORMATS,
    EmptyDocumentError,
    UnsupportedFormatError,
)
from placeinator.resumes.service import create_resume, list_resumes

router = APIRouter(prefix="/api/resumes", tags=["resumes"])


class ResumeOut(BaseModel):
    id: int
    label: str
    target_role: str | None
    version: int
    job_category: str | None
    source_format: str
    chunk_count: int

    model_config = {"from_attributes": True}


def _to_out(resume: Resume) -> ResumeOut:
    return ResumeOut(
        id=resume.id,
        label=resume.label,
        target_role=resume.target_role,
        version=resume.version,
        job_category=resume.job_category,
        source_format=resume.source_format,
        chunk_count=len(resume.chunks),
    )


def _require_profile(session: Session) -> Profile:
    profile = get_profile(session)
    if profile is None:
        raise HTTPException(
            status.HTTP_412_PRECONDITION_FAILED,
            "complete onboarding (PUT /api/profile) before adding resumes",
        )
    return profile


@router.get("", response_model=list[ResumeOut])
def read_resumes(session: Session = Depends(get_session)) -> list[ResumeOut]:
    profile = _require_profile(session)
    return [_to_out(r) for r in list_resumes(session, profile)]


@router.post("", response_model=ResumeOut, status_code=status.HTTP_201_CREATED)
async def upload_resume(
    label: str = Form(...),
    source_format: str = Form(...),
    target_role: str | None = Form(default=None),
    job_category: str | None = Form(default=None),
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> ResumeOut:
    profile = _require_profile(session)

    if source_format not in SUPPORTED_FORMATS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"source_format must be one of {SUPPORTED_FORMATS}, got {source_format!r}",
        )

    file_bytes = await file.read()
    try:
        resume = create_resume(
            session,
            profile,
            label=label,
            target_role=target_role,
            job_category=job_category,
            source_format=source_format,  # narrowed by the guard above
            file_bytes=file_bytes,
        )
    except EmptyDocumentError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except UnsupportedFormatError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    return _to_out(resume)
