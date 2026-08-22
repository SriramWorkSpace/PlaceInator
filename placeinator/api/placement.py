"""Placement automation endpoints (specification section 7)."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from placeinator.db.models import PlacementEvent, PlacementRecord
from placeinator.db.session import get_session
from placeinator.placement import auth, service
from placeinator.placement.auth import ClientSecretNotFoundError, GmailNotConnectedError
from placeinator.placement.service import PlacementNotOnboardedError
from placeinator.profile.service import get_profile

router = APIRouter(prefix="/api/placement", tags=["placement"])


class ConnectionStatusOut(BaseModel):
    connected: bool


class EventOut(BaseModel):
    id: int
    company: str
    event_type: str
    round_name: str | None
    event_date: str | None
    start_time: str | None
    end_time: str | None
    reporting_time: str | None
    venue: str | None
    meeting_link: str | None
    instructions: str | None
    calendar_event_id: str | None
    needs_review: bool


class RecordOut(BaseModel):
    id: int
    company: str | None
    status: str
    match_confidence: float
    needs_review: bool
    matched_on: list[str]
    source_document: str | None
    events: list[EventOut]


def _event_to_out(event: PlacementEvent) -> EventOut:
    return EventOut(
        id=event.id,
        company=event.company,
        event_type=event.event_type,
        round_name=event.round_name,
        event_date=event.event_date.isoformat() if event.event_date else None,
        start_time=event.start_time,
        end_time=event.end_time,
        reporting_time=event.reporting_time,
        venue=event.venue,
        meeting_link=event.meeting_link,
        instructions=event.instructions,
        calendar_event_id=event.calendar_event_id,
        needs_review=event.needs_review,
    )


def _record_to_out(record: PlacementRecord) -> RecordOut:
    return RecordOut(
        id=record.id,
        company=record.company,
        status=record.status,
        match_confidence=record.match_confidence,
        needs_review=record.needs_review,
        matched_on=record.matched_on,
        source_document=record.source_document,
        events=[_event_to_out(e) for e in record.events],
    )


def _require_record(session: Session, record_id: int) -> PlacementRecord:
    record = session.get(PlacementRecord, record_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no placement record with id {record_id}")
    return record


def _require_profile(session: Session):
    profile = get_profile(session)
    if profile is None:
        raise HTTPException(status.HTTP_412_PRECONDITION_FAILED, "complete onboarding first")
    return profile


@router.get("/status", response_model=ConnectionStatusOut)
def read_status() -> ConnectionStatusOut:
    return ConnectionStatusOut(connected=auth.is_connected())


@router.post("/connect", response_model=ConnectionStatusOut)
async def connect() -> ConnectionStatusOut:
    """Runs the interactive OAuth loopback flow -- opens the user's browser
    and blocks until they approve. Run off the event loop
    (`asyncio.to_thread`) since `auth.connect()` is a synchronous, blocking
    call by design (`google_auth_oauthlib`'s own API); this keeps uvicorn
    free to serve other requests while this one waits on the browser."""
    try:
        await asyncio.to_thread(auth.connect)
    except ClientSecretNotFoundError as exc:
        raise HTTPException(status.HTTP_412_PRECONDITION_FAILED, str(exc)) from exc
    return ConnectionStatusOut(connected=True)


@router.post("/disconnect", status_code=status.HTTP_204_NO_CONTENT)
def disconnect() -> None:
    auth.disconnect()


@router.post("/sync", status_code=status.HTTP_204_NO_CONTENT)
def sync(session: Session = Depends(get_session)) -> None:
    profile = _require_profile(session)
    try:
        service.sync(session, profile)
    except (GmailNotConnectedError, PlacementNotOnboardedError) as exc:
        raise HTTPException(status.HTTP_412_PRECONDITION_FAILED, str(exc)) from exc


@router.get("/review-queue", response_model=list[RecordOut])
def read_review_queue(session: Session = Depends(get_session)) -> list[RecordOut]:
    return [_record_to_out(r) for r in service.list_review_queue(session)]


@router.post("/review/{record_id}/confirm", response_model=RecordOut)
def confirm_review(record_id: int, session: Session = Depends(get_session)) -> RecordOut:
    record = _require_record(session, record_id)
    service.confirm_record(session, record)
    return _record_to_out(record)


@router.post("/review/{record_id}/reject", status_code=status.HTTP_204_NO_CONTENT)
def reject_review(record_id: int, session: Session = Depends(get_session)) -> None:
    record = _require_record(session, record_id)
    service.reject_record(session, record)


@router.get("/timeline", response_model=dict[str, list[RecordOut]])
def read_timeline(session: Session = Depends(get_session)) -> dict[str, list[RecordOut]]:
    return {
        company: [_record_to_out(r) for r in records]
        for company, records in service.list_timeline(session).items()
    }
