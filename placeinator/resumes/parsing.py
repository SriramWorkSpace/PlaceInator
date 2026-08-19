"""Extracts plain text from an uploaded resume file.

Every format collapses to the same output: a single text string, which is then
handed to placeinator.matching.chunking.chunk_resume_text. That function -- not
this one -- is what assigns sections and kinds; parsing here only needs to
recover readable text and (for LaTeX) preserve the byte-exact source, since the
tailoring engine splices against it.
"""

from __future__ import annotations

import io
from typing import Literal

import pdfplumber
from docx import Document

SourceFormat = Literal["pdf", "docx", "tex"]

SUPPORTED_FORMATS: tuple[SourceFormat, ...] = ("pdf", "docx", "tex")


class UnsupportedFormatError(ValueError):
    pass


class EmptyDocumentError(ValueError):
    """Raised when parsing succeeds but recovers no usable text -- almost
    always a scanned/image-only PDF, which needs OCR (out of scope until
    placement-attachment processing adds Tesseract support in M4)."""


def parse_resume_bytes(data: bytes, source_format: SourceFormat) -> str:
    if source_format == "pdf":
        text = _parse_pdf(data)
    elif source_format == "docx":
        text = _parse_docx(data)
    elif source_format == "tex":
        text = _parse_tex(data)
    else:
        raise UnsupportedFormatError(
            f"unsupported resume format: {source_format!r} "
            f"(expected one of {SUPPORTED_FORMATS})"
        )

    if not text.strip():
        raise EmptyDocumentError(
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


def _parse_tex(data: bytes) -> str:
    # .tex is kept byte-exact and verbatim: it is both the display text and the
    # authoritative splice source for placeinator.latex, so it must not be
    # reflowed, stripped of commands, or otherwise "cleaned up" here.
    return data.decode("utf-8")
