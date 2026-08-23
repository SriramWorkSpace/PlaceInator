"""LaTeX resume tailoring endpoints (specification section 5)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from placeinator.db.models import Job, Resume, TailoredResume
from placeinator.db.session import get_session
from placeinator.latex.compile import PdfCompileError, compile_tex_to_pdf
from placeinator.latex.parsing import LatexParseError
from placeinator.latex.tailoring import tailor_resume

router = APIRouter(prefix="/api/latex", tags=["latex"])


class TailorIn(BaseModel):
    resume_id: int
    job_id: int
    # Bullet.span.start values (see placeinator.latex.parsing) the user has
    # chosen to drop -- the only way content is ever omitted. Never inferred
    # from scores automatically.
    excluded_bullet_ids: list[int] = Field(default_factory=list)


class BulletOut(BaseModel):
    bullet_id: int
    text: str
    original_index: int
    new_index: int
    score: float
    suggested_removal: bool
    excluded: bool


class SectionOut(BaseModel):
    heading: str
    original_index: int
    new_index: int
    bullets: list[BulletOut]


class TailorOut(BaseModel):
    tex: str
    sections: list[SectionOut]
    requirements_matched: list[str]
    requirements_missing: list[str]


def _to_out(tailored: TailoredResume) -> TailorOut:
    log = tailored.change_log
    return TailorOut(
        tex=tailored.tex,
        sections=[SectionOut(**section) for section in log.get("sections", [])],
        requirements_matched=log.get("requirements_matched", []),
        requirements_missing=log.get("requirements_missing", []),
    )


@router.post("/tailor", response_model=TailorOut)
def tailor(data: TailorIn, session: Session = Depends(get_session)) -> TailorOut:
    resume = session.get(Resume, data.resume_id)
    if resume is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no resume with id {data.resume_id}")

    job = session.get(Job, data.job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no job with id {data.job_id}")

    try:
        tailored = tailor_resume(
            session, resume, job, excluded_bullet_ids=frozenset(data.excluded_bullet_ids)
        )
    except LatexParseError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    return _to_out(tailored)


@router.post("/tailor/pdf")
def tailor_pdf(data: TailorIn, session: Session = Depends(get_session)) -> Response:
    """Same tailoring as POST /tailor, compiled to PDF (spec section 5's PDF
    export, M3's deferred piece -- see docs/architecture.md). Recomputes the
    tailoring rather than reading a stored TailoredResume, matching
    tailor_resume's own "cheap enough to redo every call" design (its module
    docstring) -- one request in, one PDF out, no separate staleness gate."""
    resume = session.get(Resume, data.resume_id)
    if resume is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no resume with id {data.resume_id}")

    job = session.get(Job, data.job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no job with id {data.job_id}")

    try:
        tailored = tailor_resume(
            session, resume, job, excluded_bullet_ids=frozenset(data.excluded_bullet_ids)
        )
    except LatexParseError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    try:
        pdf_bytes = compile_tex_to_pdf(tailored.tex)
    except PdfCompileError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    return Response(content=pdf_bytes, media_type="application/pdf")
