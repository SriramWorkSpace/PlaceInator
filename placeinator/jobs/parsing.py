"""Extracts plain text from an uploaded job description file.

Mirrors placeinator.resumes.parsing's PDF/DOCX handling; kept as a separate
copy rather than a shared import so jobs (spec §2) and resumes (spec §3) stay
independent packages per the flat module layout, and because a JD has no
LaTeX/byte-exact-splice concern the way a resume does.
"""

from __future__ import annotations

import io
from typing import Literal

import pdfplumber
from docx import Document

JdSourceFormat = Literal["pdf", "docx"]

SUPPORTED_JD_FORMATS: tuple[JdSourceFormat, ...] = ("pdf", "docx")


class UnsupportedJdFormatError(ValueError):
    pass


class EmptyJdDocumentError(ValueError):
    """Raised when parsing succeeds but recovers no usable text -- almost
    always a scanned/image-only PDF, which needs OCR (out of scope until
    placement-attachment processing adds Tesseract support in M4)."""


def parse_jd_bytes(data: bytes, source_format: JdSourceFormat) -> str:
    if source_format == "pdf":
        text = _parse_pdf(data)
    elif source_format == "docx":
        text = _parse_docx(data)
    else:
        raise UnsupportedJdFormatError(
            f"unsupported job description format: {source_format!r} "
            f"(expected one of {SUPPORTED_JD_FORMATS})"
        )

    if not text.strip():
        raise EmptyJdDocumentError(
            "no extractable text found -- if this is a scanned/image PDF, "
            "OCR support is not available yet"
        )
    return text


def _parse_pdf(data: bytes) -> str:
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
    return "\n".join(pages)


def _parse_docx(data: bytes) -> str:
    document = Document(io.BytesIO(data))
    return "\n".join(paragraph.text for paragraph in document.paragraphs)
