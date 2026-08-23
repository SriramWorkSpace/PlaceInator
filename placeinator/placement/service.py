"""Orchestrates the placement pipeline end to end (spec §7): Gmail fetch ->
attachment parsing -> header normalization -> candidate identification ->
status classification / event extraction -> duplicate-safe persistence ->
Calendar.

Two source shapes are handled differently, deliberately:

* **A structured attachment row** (XLSX/PDF/DOCX with labeled columns) is
  reliable enough to run candidate identification *and* event extraction
  against -- Date/Venue/Time are explicit, named columns.
* **A plain email body** (no attachment, or nothing parseable) is *not* run
  through automatic event-date extraction. Verified directly before writing
  this: `dateparser.search.search_dates` produces false positives on
  ordinary prose (the word "we" alone parsed as a date in a real test
  against realistic email text). Silently creating a Calendar event from a
  wrong guessed date is worse than not creating one -- a body that mentions
  an event lands in the review queue for a human to read and act on
  instead, never a guessed date on a real calendar.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from google.oauth2.credentials import Credentials
from sqlalchemy import select
from sqlalchemy.orm import Session

from placeinator.db.models import PlacementEvent, PlacementRecord, Preferences, Profile
from placeinator.placement import (
    auth,
    calendar,
    candidates,
    classification,
    events,
    gmail,
    headers,
    ocr,
)
from placeinator.placement.gmail import FetchedMessage
from placeinator.placement.parsing import OcrUnavailableError, parse_placement_sheet_bytes

# Attachment filename extension -> parser format. Anything else (a raw
# .jpg/.png attachment, .zip, ...) is skipped -- OCR (placeinator.placement.ocr)
# only ever runs against a scanned *page inside a PDF*, not a bare image
# attachment; that's enough of an edge case to leave out of this first pass.
_EXTENSION_FORMATS: dict[str, str] = {"xlsx": "xlsx", "pdf": "pdf", "docx": "docx"}

# A plain-body message mentioning one of these gets flagged for review even
# though no event was auto-extracted -- there's likely a real event
# described in prose that a human should read and add manually.
_EVENT_KEYWORDS = ("interview", "assessment", "round", "coding test", "pre-placement")


class PlacementNotOnboardedError(ValueError):
    pass


def _require_preferences(profile: Profile) -> Preferences:
    if profile.preferences is None:
        # Mirrors placeinator.jobs.service's own guard shape -- a Preferences
        # row always exists once onboarded (profile.service creates it), so
        # this is defensive, not an expected path.
        raise PlacementNotOnboardedError("complete onboarding before syncing placement mail")
    return profile.preferences


def _guess_company_from_sender(sender: str) -> str | None:
    """Best-effort: the display-name portion of a From header ("Acme Corp
    Careers <hr@acme.com>" -> "Acme Corp Careers") is very often the
    company/recruiting-team name in real placement mail. Returns None for a
    bare address with no display name, rather than guess from the domain."""
    name, _, _ = sender.partition("<")
    name = name.strip().strip('"')
    return name or None


def sync(session: Session, profile: Profile) -> None:
    """Runs one full sync: fetch new Gmail messages, process each, persist
    results, and advance the history cursor. Safe to call repeatedly --
    already-seen messages aren't refetched (Gmail's own history cursor), and
    duplicate events are caught by PlacementEvent.dedupe_key's unique
    constraint."""
    credentials = auth.get_credentials()
    preferences = _require_preferences(profile)

    messages, new_history_id = gmail.fetch_new_messages(
        credentials, preferences.gmail_last_history_id
    )

    for message in messages:
        _process_message(session, profile, credentials, message)

    preferences.gmail_last_history_id = new_history_id
    session.flush()


def _process_message(
    session: Session, profile: Profile, credentials: Credentials, message: FetchedMessage
) -> None:
    if not classification.is_placement_related(message.subject, message.body_text):
        return

    parsed = _parse_attachments(message)
    fallback_company = _guess_company_from_sender(message.sender)

    if parsed.rows:
        for row in parsed.rows:
            normalized = headers.normalize_row(row)
            match = candidates.identify_candidate(normalized, profile)
            if match is None:
                continue
            # The row's own Company column, when present, is a far more
            # reliable signal than the sender-name guess -- it names the
            # specific company the row describes, whereas the sender's
            # display name is often the placement cell or a shared HR alias,
            # not the hiring company itself.
            company = normalized.get("company") or fallback_company
            record = _upsert_record(session, message, match, normalized.get("status", ""), company)
            extracted = events.extract_event(normalized, default_company=company or "")
            if extracted is not None:
                _upsert_event(session, credentials, record, extracted)
    elif parsed.ocr_text and candidates.mentions_candidate_in_text(parsed.ocr_text, profile):
        # A scanned attachment (no structured table, so OCR was tried as a
        # fallback -- see placeinator.placement.ocr) that plausibly mentions
        # the candidate. Deliberately below AUTO_ACCEPT_CONFIDENCE no matter
        # what: OCR'd text is meaningfully less reliable evidence than a
        # real structured field match, so this always lands in the review
        # queue for a human to read the original scan and decide, matching
        # this module's own confidence-gating philosophy for anything less
        # certain than that.
        match = candidates.CandidateMatch(
            confidence=candidates.MINIMUM_CONFIDENCE, matched_on=("ocr_text",)
        )
        _upsert_record(session, message, match, parsed.ocr_text, fallback_company)
    else:
        # No structured attachment -- the message landed in this connected
        # mailbox, which is itself the identifying signal (one profile per
        # connected inbox); status comes from the body text.
        match = candidates.CandidateMatch(confidence=1.0, matched_on=("inbox",))
        record = _upsert_record(session, message, match, message.body_text, fallback_company)
        haystack = f"{message.subject}\n{message.body_text}".lower()
        if any(keyword in haystack for keyword in _EVENT_KEYWORDS):
            # A human should read this and add the event manually -- see
            # this module's docstring for why no date is auto-extracted here.
            record.needs_review = True

    session.flush()


@dataclass(frozen=True)
class _ParsedAttachments:
    rows: list[dict[str, str]] = field(default_factory=list)
    # Newline-joined OCR output across every scanned PDF attachment on this
    # message -- never structured into rows, see placeinator.placement.ocr's
    # own module docstring for why.
    ocr_text: str = ""


def _parse_attachments(message: FetchedMessage) -> _ParsedAttachments:
    rows: list[dict[str, str]] = []
    ocr_texts: list[str] = []

    for attachment in message.attachments:
        has_extension = "." in attachment.filename
        extension = attachment.filename.rsplit(".", 1)[-1].lower() if has_extension else ""
        source_format = _EXTENSION_FORMATS.get(extension)
        if source_format is None:
            continue

        try:
            attachment_rows = parse_placement_sheet_bytes(attachment.data, source_format)  # type: ignore[arg-type]
        except (OcrUnavailableError, ValueError):
            # A malformed or unreadable attachment shouldn't fail the whole
            # sync -- the message's own body is still processed.
            attachment_rows = []

        if attachment_rows:
            rows.extend(attachment_rows)
        elif source_format == "pdf":
            # No extractable table. Try OCR -- XLSX/DOCX don't get this
            # fallback: XLSX is never a scan, and a scanned DOCX (an
            # embedded picture, not a real page image) is enough of an edge
            # case to leave out of this first pass rather than build and
            # verify a second detection path for it.
            try:
                text = ocr.extract_text_via_ocr(attachment.data)
            except OcrUnavailableError:
                text = ""
            if text:
                ocr_texts.append(text)

    return _ParsedAttachments(rows=rows, ocr_text="\n".join(ocr_texts))


def _upsert_record(
    session: Session,
    message: FetchedMessage,
    match: candidates.CandidateMatch,
    status_text: str,
    company: str | None,
) -> PlacementRecord:
    record = session.execute(
        select(PlacementRecord).where(PlacementRecord.gmail_message_id == message.message_id)
    ).scalar_one_or_none()
    if record is None:
        record = PlacementRecord(gmail_message_id=message.message_id)
        session.add(record)

    record.company = company
    record.status = classification.classify_status(status_text)
    record.match_confidence = match.confidence
    record.needs_review = match.needs_review
    record.matched_on = list(match.matched_on)
    record.source_document = message.subject
    return record


def _upsert_event(
    session: Session,
    credentials: Credentials,
    record: PlacementRecord,
    extracted: events.ExtractedEvent,
) -> None:
    existing = session.execute(
        select(PlacementEvent).where(PlacementEvent.dedupe_key == extracted.dedupe_key)
    ).scalar_one_or_none()
    if existing is not None:
        return  # already known -- the dedupe key IS the duplicate check

    event = PlacementEvent(
        record=record,
        company=extracted.company,
        event_type=extracted.event_type,
        round_name=extracted.round_name,
        event_date=extracted.event_date,
        start_time=extracted.start_time,
        end_time=extracted.end_time,
        reporting_time=extracted.reporting_time,
        venue=extracted.venue,
        meeting_link=extracted.meeting_link,
        instructions=extracted.instructions,
        dedupe_key=extracted.dedupe_key,
        extraction_confidence=record.match_confidence,
        needs_review=record.needs_review,
    )
    session.add(event)
    session.flush()

    if not event.needs_review:
        event.calendar_event_id = calendar.create_event(credentials, extracted)


def _as_extracted_event(event: PlacementEvent) -> events.ExtractedEvent:
    return events.ExtractedEvent(
        company=event.company,
        event_type=event.event_type,
        round_name=event.round_name,
        event_date=event.event_date,
        start_time=event.start_time,
        end_time=event.end_time,
        reporting_time=event.reporting_time,
        venue=event.venue,
        meeting_link=event.meeting_link,
        instructions=event.instructions,
        dedupe_key=event.dedupe_key,
    )


def confirm_record(session: Session, record: PlacementRecord) -> None:
    """Confirms a review-queue item: clears the review flag and, for any
    linked event not yet on the calendar, creates it now -- calendar
    creation for a reviewed item only ever happens after this explicit
    confirmation, never automatically during sync."""
    credentials = auth.get_credentials()
    record.needs_review = False
    for event in record.events:
        event.needs_review = False
        if event.calendar_event_id is None and event.event_date is not None:
            event.calendar_event_id = calendar.create_event(credentials, _as_extracted_event(event))
    session.flush()


def reject_record(session: Session, record: PlacementRecord) -> None:
    session.delete(record)
    session.flush()


def list_review_queue(session: Session) -> list[PlacementRecord]:
    return list(
        session.execute(select(PlacementRecord).where(PlacementRecord.needs_review.is_(True))).scalars()
    )


def list_timeline(session: Session) -> dict[str, list[PlacementRecord]]:
    """Records grouped by company, most-recently-updated first within each
    company -- the spec's own company-progression view."""
    records = session.execute(
        select(PlacementRecord)
        .where(PlacementRecord.company.is_not(None))
        .order_by(PlacementRecord.updated_at.desc())
    ).scalars()

    timeline: dict[str, list[PlacementRecord]] = {}
    for record in records:
        assert record.company is not None  # guaranteed by the WHERE clause above
        timeline.setdefault(record.company, []).append(record)
    return timeline
