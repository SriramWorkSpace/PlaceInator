"""Candidate identification (spec §7): does the current user appear in this
placement-sheet row?

Signals are weighted by reliability, not treated as all-or-nothing: an exact
email or student-ID match is far stronger evidence than a fuzzy name match,
so each contributes a different share of the confidence score. Below
`AUTO_ACCEPT_CONFIDENCE` the caller (`placeinator.placement.service`) sets
`PlacementRecord.needs_review` rather than acting on a guess -- spec's own
words: "Produce a confidence score for ambiguous matches."

Weights are calibrated against the spec's own worked example (its
"Document Structure Detection" table has only a name column, no email or
student ID) -- a name-only sheet is the *common* case, not the fallback, so
a single strong name match must still clear the review-queue floor on its
own rather than always being silently discarded.
"""

from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz

from placeinator.db.models import Profile
from placeinator.placement.headers import CanonicalField

# Per-signal contribution. Email and student ID are exact-match-or-nothing;
# a name match is scaled by its own fuzzy similarity, so a marginal name
# match contributes less than a near-exact one.
_EMAIL_WEIGHT = 0.45
_STUDENT_ID_WEIGHT = 0.35
_NAME_WEIGHT = 0.35

# A fuzzy name match below this similarity doesn't count at all -- distinct
# from a low *confidence* score, this is "not plausibly the same name".
_NAME_SIMILARITY_FLOOR = 0.8

# Below this confidence, the row isn't a candidate match at all -- not even
# into the review queue. Set so that any name match that clears the
# similarity floor above always reaches at least this bar
# (_NAME_WEIGHT * _NAME_SIMILARITY_FLOOR = 0.28), since spec lists a strong
# name match as sufficient grounds for a human to review, on its own.
MINIMUM_CONFIDENCE = 0.25

# At or above this, the match is accepted without review. A single signal
# alone (email OR student_id OR a strong name) never reaches this --
# corroboration from a second signal is what auto-accept actually means
# here, matching spec's "ambiguous matches" framing for anything less.
AUTO_ACCEPT_CONFIDENCE = 0.7


@dataclass(frozen=True)
class CandidateMatch:
    confidence: float
    matched_on: tuple[str, ...]

    @property
    def needs_review(self) -> bool:
        return self.confidence < AUTO_ACCEPT_CONFIDENCE


def _normalize_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


def identify_candidate(row: dict[CanonicalField, str], profile: Profile) -> CandidateMatch | None:
    """None means the row doesn't plausibly reference this candidate at all
    (confidence below MINIMUM_CONFIDENCE) -- distinct from a low-but-real
    confidence, which still produces a CandidateMatch for the review queue.
    """
    matched_on: list[str] = []
    score = 0.0

    row_email = row.get("email", "").strip().lower()
    if row_email and profile.email and row_email == profile.email.strip().lower():
        score += _EMAIL_WEIGHT
        matched_on.append("email")

    row_student_id = row.get("student_id", "").strip().lower()
    profile_student_id = (profile.student_id or "").strip().lower()
    if row_student_id and profile_student_id and row_student_id == profile_student_id:
        score += _STUDENT_ID_WEIGHT
        matched_on.append("student_id")

    row_candidate = row.get("candidate", "")
    if row_candidate:
        candidate_names = [profile.full_name, *profile.name_aliases]
        best_similarity = max(
            (
                fuzz.ratio(_normalize_name(row_candidate), _normalize_name(name)) / 100
                for name in candidate_names
                if name
            ),
            default=0.0,
        )
        if best_similarity >= _NAME_SIMILARITY_FLOOR:
            score += _NAME_WEIGHT * best_similarity
            matched_on.append("name")

    confidence = min(1.0, score)
    if confidence < MINIMUM_CONFIDENCE:
        return None
    return CandidateMatch(confidence=confidence, matched_on=tuple(matched_on))
