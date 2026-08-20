"""Best-effort personal-detail extraction from resume text, for onboarding
autofill only.

Regex/heuristic, not a parser -- there is no LLM anywhere in this project (see
docs/decisions.md#adr-0002--deterministic-engine-no-llm-generation) and this is
no exception. Every field is independently optional: a field with no confident
match is left null rather than guessed, since the caller always prefills a form
the user reviews and can edit before anything is saved.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# A leading digit/+ then a run of digit/space/paren/dash/dot characters: loose
# enough to catch "+91 98765 43210" and "(415) 555-0199" alike. The digit-count
# guard below (10-13) is what rules out false positives like a bare year.
_PHONE_RE = re.compile(r"\+?\d[\d\s().-]{7,14}\d")
_COLLEGE_KEYWORDS = ("university", "college", "institute of technology", "institute", "iit", "nit")
_SECTION_HEADINGS = frozenset(
    {
        "summary",
        "objective",
        "profile",
        "contact",
        "skills",
        "experience",
        "education",
        "projects",
        "certifications",
        "achievements",
        "publications",
        "awards",
        "interests",
        "references",
    }
)
_DEGREE_DEPARTMENT_RE = re.compile(
    r"\b(?:B\.?\s?Tech|M\.?\s?Tech|B\.?\s?E|M\.?\s?E|B\.?\s?Sc|M\.?\s?Sc|B\.?\s?A|M\.?\s?A|MBA|"
    r"Bachelor(?:'s)?|Master(?:'s)?|Ph\.?\s?D)"
    # Stop at the first comma/newline so a trailing ", Some University, 2024"
    # doesn't get folded into the department name.
    r"[^\n,]{0,20}?\bin\b\s+([A-Za-z][A-Za-z &-]{2,60})",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ExtractedProfileFields:
    full_name: str | None
    email: str | None
    phone: str | None
    college: str | None
    department: str | None


def extract_profile_fields(text: str) -> ExtractedProfileFields:
    """Scan raw resume text for a header-block name, contact details, and
    education, using only patterns that are unambiguous enough to trust
    without a human already having confirmed them."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    email = _find_email(text)
    phone = _find_phone(text)
    return ExtractedProfileFields(
        full_name=_find_name(lines),
        email=email,
        phone=phone,
        college=_find_college(lines),
        department=_find_department(text),
    )


def _find_email(text: str) -> str | None:
    match = _EMAIL_RE.search(text)
    return match.group(0) if match else None


def _find_phone(text: str) -> str | None:
    for match in _PHONE_RE.finditer(text):
        digits = re.sub(r"\D", "", match.group(0))
        # A bare 3-4 digit run (e.g. a year, a room number) is not a phone
        # number; most real numbers, with country code, land in 10-13 digits.
        if 10 <= len(digits) <= 13:
            return match.group(0).strip()
    return None


def _find_name(lines: list[str]) -> str | None:
    # The resume header is almost always the candidate's name: the first
    # non-empty line that isn't itself an email/phone and looks like a name
    # (2-5 alphabetic words, no digits or section-heading punctuation).
    for line in lines[:5]:
        if _EMAIL_RE.search(line) or _PHONE_RE.search(line):
            continue
        if ":" in line:
            # A real name is never "Label: value" -- that shape belongs to a
            # section heading ("Skills: ...") or a contact-details line.
            continue
        if line.strip(" ,.").lower() in _SECTION_HEADINGS:
            continue
        words = line.split()
        if 1 <= len(words) <= 5 and all(_looks_like_name_word(w) for w in words):
            return line.strip(" ,.")
    return None


def _looks_like_name_word(word: str) -> bool:
    # Title Case throughout, not just the first word, is what separates an
    # actual name ("Jane Doe") from a sentence fragment ("Backend engineer").
    stripped = word.strip(".,:")
    return stripped.isalpha() and stripped[:1].isupper()


def _find_college(lines: list[str]) -> str | None:
    for line in lines:
        lowered = line.lower()
        if any(keyword in lowered for keyword in _COLLEGE_KEYWORDS):
            return line.strip(" ,.")
    return None


def _find_department(text: str) -> str | None:
    match = _DEGREE_DEPARTMENT_RE.search(text)
    return match.group(1).strip(" ,.") if match else None
