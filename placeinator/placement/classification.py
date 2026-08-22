"""Email and status classification (spec §7), keyword-rule based -- no LLM
anywhere in this path (ADR 0002).

Two separate classifications happen here:

1. **Is this email placement-related at all?** (Gmail Monitoring's own
   category list: shortlists, eligibility lists, interview announcements,
   assessments, rounds, pre-placement talks, offers, rejections.) A coarse
   relevance filter -- decides whether to bother running the rest of the
   pipeline on a message, nothing more.
2. **What status does the wording imply?** (Placement Status Classification's
   exact phrase lists, quoted close to verbatim from spec.) Applied to
   whichever text actually names the candidate -- the email body, or a
   placement-sheet row's Status column.
"""

from __future__ import annotations

from placeinator.db.enums import PlacementStatus

# Gmail Monitoring's own category list (spec §7). Used only to decide
# whether a message is worth running the rest of the pipeline on -- never to
# set a specific status by itself.
_PLACEMENT_KEYWORDS = (
    "shortlist",
    "eligib",
    "interview",
    "assessment",
    "technical round",
    "hr round",
    "pre-placement",
    "pre placement",
    "placement",
    "offer",
    "reject",
    "not selected",
    "selection",
    "recruitment",
    "campus drive",
    "hiring",
)

# Status wording, quoted close to verbatim from spec's "Placement Status
# Classification" section (a handful of common real-world phrasings added
# alongside the exact spec examples). REJECTED is checked before
# SHORTLISTED specifically because "not shortlisted"/"not selected" contain
# a positive keyword as a substring ("shortlisted", "selected") -- confirmed
# by a real test failure, not a hypothetical: checking SHORTLISTED first
# classified "Not shortlisted" as SHORTLISTED.
_SHORTLISTED_PHRASES = (
    "shortlisted",
    "selected for interview",
    "eligible for technical round",
    "called for interview",
    "you have been selected",
)
_REJECTED_PHRASES = (
    "rejected",
    "not selected",
    "not shortlisted",
    "unfortunately",
    "will not be moving forward",
    "not proceeding",
)
_PENDING_PHRASES = (
    "under review",
    "waitlisted",
    "result pending",
    "will be notified",
)


def is_placement_related(subject: str, body: str) -> bool:
    haystack = f"{subject}\n{body}".lower()
    return any(keyword in haystack for keyword in _PLACEMENT_KEYWORDS)


def classify_status(text: str) -> PlacementStatus:
    lowered = text.lower()
    if any(phrase in lowered for phrase in _REJECTED_PHRASES):
        return PlacementStatus.REJECTED
    if any(phrase in lowered for phrase in _SHORTLISTED_PHRASES):
        return PlacementStatus.SHORTLISTED
    if any(phrase in lowered for phrase in _PENDING_PHRASES):
        return PlacementStatus.PENDING
    return PlacementStatus.UNKNOWN
