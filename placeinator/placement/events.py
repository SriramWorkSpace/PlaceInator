"""Event extraction and duplicate detection (spec §7).

Extracts Company/EventType/Round/Date/Times/Venue/Link/Instructions from a
normalized placement-sheet row (`placeinator.placement.headers`) via keyword
rules + `dateparser` -- no LLM anywhere (ADR 0002). Computes the dedupe key
the schema already enforces uniqueness on (`PlacementEvent.dedupe_key`, see
that column's own comment in `db/models.py`), so "duplicate detection"
(spec) really means: the caller upserts against that existing unique
constraint rather than blind-inserting. The DB does the actual enforcement;
this module only has to compute the key consistently.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date

import dateparser

from placeinator.db.enums import EventType
from placeinator.placement.headers import CanonicalField

# Spec's own "Possible events" list (§7). Checked in this order -- first
# match wins -- against whatever text names the event/round.
_EVENT_TYPE_KEYWORDS: tuple[tuple[str, EventType], ...] = (
    ("coding test", EventType.CODING_TEST),
    ("coding round", EventType.CODING_TEST),
    ("assessment", EventType.ASSESSMENT),
    ("technical round", EventType.TECHNICAL_ROUND),
    ("technical interview", EventType.TECHNICAL_ROUND),
    ("hr round", EventType.HR_ROUND),
    ("hr interview", EventType.HR_ROUND),
    ("pre-placement talk", EventType.PRE_PLACEMENT_TALK),
    ("pre placement talk", EventType.PRE_PLACEMENT_TALK),
    ("ppt", EventType.PRE_PLACEMENT_TALK),
    ("interview", EventType.INTERVIEW),
)


@dataclass(frozen=True)
class ExtractedEvent:
    company: str
    event_type: EventType
    round_name: str | None
    event_date: date | None
    start_time: str | None
    end_time: str | None
    reporting_time: str | None
    venue: str | None
    meeting_link: str | None
    instructions: str | None
    dedupe_key: str


def classify_event_type(text: str) -> EventType:
    lowered = text.lower()
    for keyword, event_type in _EVENT_TYPE_KEYWORDS:
        if keyword in lowered:
            return event_type
    return EventType.OTHER


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    parsed = dateparser.parse(value)
    return parsed.date() if parsed else None


def _parse_time(value: str | None) -> str | None:
    """Returns a HH:MM 24-hour string, or None. PlacementEvent.start_time/
    end_time/reporting_time are String(16) columns -- a display string, not
    a full datetime, since a placement event's date and time often come
    from separate sheet columns rather than one combined value."""
    if not value:
        return None
    parsed = dateparser.parse(value)
    return parsed.strftime("%H:%M") if parsed else None


def compute_dedupe_key(
    company: str, event_type: EventType, event_date: date | None, start_time: str | None
) -> str:
    """sha256(company, event_type, date, start_time) -- see
    PlacementEvent.dedupe_key's own comment in db/models.py. Company text is
    lowercased/stripped first so "Acme Corp" and "acme corp " don't produce
    different keys for what is really the same event."""
    parts = "|".join(
        [
            company.strip().lower(),
            event_type.value,
            event_date.isoformat() if event_date else "",
            start_time or "",
        ]
    )
    return hashlib.sha256(parts.encode("utf-8")).hexdigest()


def extract_event(
    row: dict[CanonicalField, str], *, default_company: str = ""
) -> ExtractedEvent | None:
    """None when the row doesn't carry enough to identify an event at all
    (no company and no recognizable event-type wording) -- a row can be a
    valid candidate-status update without describing an event."""
    company = row.get("company", default_company).strip()
    round_name = row.get("round")
    event_type_source = " ".join(filter(None, [row.get("event_type"), round_name]))
    event_type = classify_event_type(event_type_source) if event_type_source else EventType.OTHER

    if not company and event_type == EventType.OTHER:
        return None

    event_date = _parse_date(row.get("event_date"))
    start_time = _parse_time(row.get("start_time"))

    return ExtractedEvent(
        company=company,
        event_type=event_type,
        round_name=round_name,
        event_date=event_date,
        start_time=start_time,
        end_time=_parse_time(row.get("end_time")),
        reporting_time=_parse_time(row.get("reporting_time")),
        venue=row.get("venue"),
        meeting_link=row.get("meeting_link"),
        instructions=row.get("instructions"),
        dedupe_key=compute_dedupe_key(company, event_type, event_date, start_time),
    )
