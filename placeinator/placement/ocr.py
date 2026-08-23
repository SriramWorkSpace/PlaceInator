"""OCR fallback for scanned PDF placement-sheet attachments (spec section 7,
deferred at M4).

Text-only, deliberately not table-structure-reconstructing: a scanned
table's row/column layout (skew, merged cells, inconsistent spacing) is far
less reliable to recover than pdfplumber's real table extraction already
gives for a digital PDF, and this module's own stakes -- a false positive
here tells someone they were shortlisted when they were not, see
placeinator.placement's package docstring -- make guessing at structure the
wrong tradeoff. Every OCR'd attachment routes straight to the review queue,
never auto-accepted, regardless of match strength (see
placeinator.placement.service's OCR fallback and
placeinator.placement.candidates.mentions_candidate_in_text).

Uses RapidOCR (github.com/RapidAI/RapidOCR) rather than a Tesseract
subprocess: a pure onnxruntime pipeline (ADR 0005: ONNX Runtime only,
PyTorch must never enter the dependency tree), and its ONNX models ship
inside the pip wheel itself (~12 MB) -- no separate runtime download, unlike
the embedding model or the bundled Tectonic PDF engine, and no external
binary/subprocess to detect or bundle at all.
"""

from __future__ import annotations

from functools import lru_cache
from io import BytesIO

import numpy as np
import pdfplumber
from rapidocr_onnxruntime import RapidOCR

from placeinator.placement.parsing import OcrUnavailableError

# A scanned page renders to an image at this DPI before OCR -- high enough
# for legible text recognition on a typical placement-sheet scan without
# ballooning memory/time on a long, multi-page PDF.
_OCR_RESOLUTION = 200


@lru_cache(maxsize=1)
def _engine() -> RapidOCR:
    try:
        return RapidOCR()
    except Exception as exc:
        raise OcrUnavailableError(f"could not initialize the OCR engine: {exc}") from exc


def _is_scanned_page(page: pdfplumber.page.Page) -> bool:
    """A page with a real text layer has .chars populated; a scan is (almost
    always) one big embedded image with no text layer at all. Checking
    .chars rather than extract_text() == "" -- a page of only whitespace
    characters would extract_text() to "" too, but still isn't a scan and
    doesn't need OCR."""
    return not page.chars and bool(page.images)


def extract_text_via_ocr(pdf_bytes: bytes) -> str:
    """Runs OCR over every page that looks scanned (see _is_scanned_page)
    and concatenates the recognized text, newline-separated. Returns "" if
    no page looked scanned, or OCR recognized nothing on any of them --
    both mean the same thing to the caller (nothing usable came out of this
    attachment), so neither is treated as an error."""
    engine = _engine()
    texts: list[str] = []

    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            if not _is_scanned_page(page):
                continue
            image = page.to_image(resolution=_OCR_RESOLUTION).original.convert("RGB")
            result, _elapsed = engine(np.array(image))
            if result:
                texts.extend(line[1] for line in result)

    return "\n".join(texts)
