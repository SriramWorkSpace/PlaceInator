"""Header normalization for placement sheets (spec §7).

Recognizes column-name variants ("Student Name", "Applicant" -> candidate)
via a synonym dictionary first, falling back to `rapidfuzz` fuzzy matching
against that same dictionary for anything not named explicitly -- exactly
ADR 0002's "header-synonym dictionary + rapidfuzz fuzzy matching" commitment
for placement extraction. No LLM anywhere in this path.

Deliberately conservative: a header that doesn't clear the fuzzy-match
threshold is dropped, not guessed -- a wrong column mapping here silently
misattributes a value to the wrong field, which is worse than losing it.
"""

from __future__ import annotations

import re
from typing import Literal

from rapidfuzz import fuzz, process

CanonicalField = Literal[
    "candidate",
    "email",
    "student_id",
    "college",
    "department",
    "status",
    "company",
    "event_type",
    "round",
    "event_date",
    "start_time",
    "end_time",
    "reporting_time",
    "venue",
    "meeting_link",
    "instructions",
]

CANONICAL_FIELDS: tuple[CanonicalField, ...] = (
    "candidate",
    "email",
    "student_id",
    "college",
    "department",
    "status",
    "company",
    "event_type",
    "round",
    "event_date",
    "start_time",
    "end_time",
    "reporting_time",
    "venue",
    "meeting_link",
    "instructions",
)

# Exact-match synonyms, lowercased and whitespace-collapsed before lookup.
# Not exhaustive by design -- the rapidfuzz fallback below catches near
# misses (typos, minor rewording) this dictionary doesn't name explicitly.
_HEADER_SYNONYMS: dict[str, CanonicalField] = {
    "candidate name": "candidate",
    "student name": "candidate",
    "applicant": "candidate",
    "applicant name": "candidate",
    "name": "candidate",
    "email": "email",
    "email address": "email",
    "email id": "email",
    "student id": "student_id",
    "registration number": "student_id",
    "registration id": "student_id",
    "roll number": "student_id",
    "roll no": "student_id",
    "college": "college",
    "institution": "college",
    "department": "department",
    "branch": "department",
    "result": "status",
    "status": "status",
    "selection status": "status",
    "outcome": "status",
    "company": "company",
    "organization": "company",
    "employer": "company",
    "event type": "event_type",
    "round": "round",
    "interview round": "round",
    "interview date": "event_date",
    "date": "event_date",
    "schedule": "event_date",
    "event date": "event_date",
    "start time": "start_time",
    "time": "start_time",
    "end time": "end_time",
    "reporting time": "reporting_time",
    "venue": "venue",
    "location": "venue",
    "meeting link": "meeting_link",
    "link": "meeting_link",
    "zoom link": "meeting_link",
    "instructions": "instructions",
    "notes": "instructions",
}

# Below this rapidfuzz score (0-100), a header is left unrecognized rather
# than guessed.
_FUZZY_MATCH_THRESHOLD = 80.0

_WHITESPACE_RE = re.compile(r"\s+")


def _normalize(header: str) -> str:
    return _WHITESPACE_RE.sub(" ", header.strip().lower())


def classify_header(header: str) -> CanonicalField | None:
    normalized = _normalize(header)
    exact = _HEADER_SYNONYMS.get(normalized)
    if exact is not None:
        return exact

    match = process.extractOne(
        normalized,
        _HEADER_SYNONYMS.keys(),
        scorer=fuzz.ratio,
        score_cutoff=_FUZZY_MATCH_THRESHOLD,
    )
    if match is None:
        return None
    matched_synonym = match[0]
    return _HEADER_SYNONYMS[matched_synonym]


def normalize_row(row: dict[str, str]) -> dict[CanonicalField, str]:
    """Maps a raw parsed row (real header text -> value) to canonical
    fields. An unrecognized header's value is dropped, not misattributed."""
    normalized: dict[CanonicalField, str] = {}
    for header, value in row.items():
        field = classify_header(header)
        if field is not None and value:
            normalized[field] = value
    return normalized
