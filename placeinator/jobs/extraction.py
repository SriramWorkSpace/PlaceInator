"""Best-effort designation/company extraction from an uploaded JD file, for
form autofill only.

Regex/heuristic, not a parser -- no LLM anywhere in this project (see
docs/decisions.md#adr-0002--deterministic-engine-no-llm-generation). A JD's
layout is far less standardized than a resume's header block, so this is
deliberately conservative: a field with no confident match stays null rather
than guessed, since the caller always prefills a form the user reviews and
edits before saving -- the full extracted text (returned separately by the
caller) is what actually matters for matching, not these two fields.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_LABELED_COMPANY_RE = re.compile(
    r"^(?:company|organi[sz]ation|employer)\s*[:\-]\s*(.+)$", re.IGNORECASE
)
_ABOUT_COMPANY_RE = re.compile(r"^about\s+(.+?)[:\-]?\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class ExtractedJobFields:
    designation: str | None
    company: str | None


def extract_job_fields(text: str) -> ExtractedJobFields:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return ExtractedJobFields(
        designation=_find_designation(lines),
        company=_find_company(lines),
    )


def _find_designation(lines: list[str]) -> str | None:
    # A JD's header line is almost always the role title: short, and not
    # itself a "Company: ..." / "About ..." label or a full sentence.
    for line in lines[:5]:
        if _LABELED_COMPANY_RE.match(line) or _ABOUT_COMPANY_RE.match(line):
            continue
        if line.endswith((".", ":", ";")):
            continue
        words = line.split()
        if 1 <= len(words) <= 8:
            return line.strip(" ,.")
    return None


def _find_company(lines: list[str]) -> str | None:
    for line in lines[:15]:
        match = _LABELED_COMPANY_RE.match(line) or _ABOUT_COMPANY_RE.match(line)
        if match:
            return match.group(1).strip(" ,.")
    return None
