"""placeinator.placement.ocr -- scanned-PDF text fallback via the real,
bundled RapidOCR engine (not mocked). Its ONNX models ship inside the
rapidocr-onnxruntime wheel itself, so unlike the embedding model or the
bundled Tectonic PDF engine, there's no runtime download to avoid here --
these run in the regular suite, no `model` marker needed (timed during
development: ~1s total, dominated by one-time engine construction).

Fixtures are real image-only PDFs built with Pillow, the same "build a real
file with the library that writes it" convention
tests/unit/test_placement_parsing.py already uses for XLSX/DOCX fixtures --
an image-only PDF (no text layer) is exactly what a scanned document is.
`_is_scanned_page` itself is tested against lightweight stand-ins rather
than a hand-built "real digital PDF": no PDF-writing library is a project
dependency, and a hand-rolled raw PDF byte stream turned out to be exactly
as fragile as it sounds (missing xref table, first attempt) -- not worth
that risk for testing two attribute checks.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

from PIL import Image, ImageDraw

from placeinator.placement.ocr import _is_scanned_page, extract_text_via_ocr


def _scanned_pdf_bytes(lines: list[str]) -> bytes:
    image = Image.new("RGB", (800, 60 + 40 * len(lines)), color="white")
    draw = ImageDraw.Draw(image)
    for i, line in enumerate(lines):
        draw.text((20, 20 + 40 * i), line, fill="black")
    buf = io.BytesIO()
    image.save(buf, "PDF")
    return buf.getvalue()


@dataclass
class _FakePage:
    """Stands in for pdfplumber.page.Page -- _is_scanned_page only ever
    touches .chars and .images, so a real parsed PDF is unnecessary here."""

    chars: list[object] = field(default_factory=list)
    images: list[object] = field(default_factory=list)


def test_is_scanned_page_true_for_an_image_with_no_text_layer():
    assert _is_scanned_page(_FakePage(chars=[], images=[object()])) is True


def test_is_scanned_page_false_for_a_real_text_layer():
    assert _is_scanned_page(_FakePage(chars=[object()], images=[object()])) is False


def test_is_scanned_page_false_for_a_blank_page_with_no_image_either():
    """Empty .chars alone doesn't mean "scanned" -- a genuinely blank page
    (no text, no embedded image) isn't a scan, just an empty page."""
    assert _is_scanned_page(_FakePage(chars=[], images=[])) is False


def test_extract_text_via_ocr_reads_a_scanned_page():
    pdf_bytes = _scanned_pdf_bytes(
        ["Placement Shortlist", "Jane Doe - SHORTLISTED", "Company: Acme Corp"]
    )
    text = extract_text_via_ocr(pdf_bytes)
    assert "Jane Doe" in text
    assert "SHORTLISTED" in text


def test_extract_text_via_ocr_returns_empty_for_a_blank_scanned_page():
    pdf_bytes = _scanned_pdf_bytes([])
    assert extract_text_via_ocr(pdf_bytes) == ""
