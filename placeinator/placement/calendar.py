"""Google Calendar event creation (spec §7), using the same OAuth credential
Gmail sync uses (`calendar.events` scope -- event creation only, never full
calendar control).
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

import tzlocal
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from placeinator.placement.events import ExtractedEvent

_CALENDAR_ID = "primary"

# Google Calendar rejects a naive dateTime with no accompanying timeZone --
# assuming UTC would misplace every event by the difference from this
# machine's real timezone. tzlocal comes in as a transitive dependency of
# dateparser (confirmed installed), so no new dependency is needed for this.
_LOCAL_TIMEZONE = tzlocal.get_localzone_name()


def _service(credentials: Credentials):
    return build("calendar", "v3", credentials=credentials, cache_discovery=False)


def _parse_hhmm(value: str | None) -> time | None:
    if not value:
        return None
    hour, minute = (int(p) for p in value.split(":"))
    return time(hour, minute)


def create_event(credentials: Credentials, event: ExtractedEvent) -> str | None:
    """Creates a Calendar event and returns its id, or None if there's not
    enough to schedule (no date) -- a candidate-status update with no date
    isn't a calendar-worthy event."""
    if event.event_date is None:
        return None

    start_dt = datetime.combine(event.event_date, _parse_hhmm(event.start_time) or time(9, 0))
    end_time = _parse_hhmm(event.end_time)
    # No extracted end time: default to a 1-hour block rather than a
    # zero-duration event (reusing start_time as end_time would create one).
    end_dt = (
        datetime.combine(event.event_date, end_time)
        if end_time
        else start_dt + timedelta(hours=1)
    )

    body = {
        "summary": f"{event.event_type.value.replace('_', ' ').title()} — {event.company}",
        "description": event.instructions or "",
        "location": event.venue or event.meeting_link or "",
        "start": {"dateTime": start_dt.isoformat(), "timeZone": _LOCAL_TIMEZONE},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": _LOCAL_TIMEZONE},
    }
    service = _service(credentials)
    created = service.events().insert(calendarId=_CALENDAR_ID, body=body).execute()
    return created["id"]
