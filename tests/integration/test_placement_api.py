"""Exercises the placement API through the real ASGI app and a real,
Alembic-migrated SQLite database, with the external boundaries mocked --
same shape as tests/integration/test_ats_feed_api.py and
test_jobs_search_api.py: patch the *module's own imported name*, not the
library globally, and let everything above that boundary run for real
(FastAPI routing, auth, ORM persistence, the dedupe unique constraint).

Three boundaries are mocked here, all for the same reason (no real network,
no real OS keychain mutation from an automated test run):

* `placeinator.placement.auth` (keyring) -- an in-memory dict stands in for
  the OS keychain, so the test suite never reads or writes the real one.
* `placeinator.placement.gmail.fetch_new_messages` -- returns canned
  FetchedMessage objects rather than hitting the real Gmail API. This is a
  higher-level patch point than mocking HTTP transport (c.f. ats_feed's
  httpx.MockTransport), deliberately: googleapiclient's own wire format is
  Google's problem to test, not this app's -- what this app owns is
  everything from a FetchedMessage onward, which is exactly what stays real.
* `placeinator.placement.calendar.create_event` -- returns a fake event id
  rather than creating a real Calendar event.

model-marked: persistence for a structured attachment goes through
placement.headers/candidates, pure logic with no model dependency, but the
fixture setup mirrors test_ats_feed_api.py's real-migrated-DB pattern, which
this project keeps model-marked for consistency with its sibling API tests.
"""

from __future__ import annotations

import io

import openpyxl
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from PIL import Image, ImageDraw

from placeinator.app import create_app
from placeinator.db.migrate import upgrade_to_head
from placeinator.placement.gmail import FetchedAttachment, FetchedMessage
from placeinator.security import generate_token

pytestmark = [pytest.mark.model, pytest.mark.asyncio]


def _xlsx_bytes(rows: list[list[object]]) -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    buf = io.BytesIO()
    workbook.save(buf)
    return buf.getvalue()


def _scanned_pdf_bytes(lines: list[str]) -> bytes:
    """An image-only PDF (no text layer) -- exactly what a scanned document
    is. Same builder as tests/unit/test_placement_ocr.py, duplicated rather
    than imported, matching this file's own precedent for _xlsx_bytes
    (also duplicated from tests/unit/test_placement_parsing.py)."""
    image = Image.new("RGB", (800, 60 + 40 * len(lines)), color="white")
    draw = ImageDraw.Draw(image)
    for i, line in enumerate(lines):
        draw.text((20, 20 + 40 * i), line, fill="black")
    buf = io.BytesIO()
    image.save(buf, "PDF")
    return buf.getvalue()


class _FakeCredentials:
    """A stand-in for google.oauth2.credentials.Credentials -- the mocked
    fetch/create_event functions never actually inspect it, but service.py's
    real code still passes it through, so it needs to exist as *something*."""


@pytest.fixture
def _fake_keyring(monkeypatch):
    """An in-memory dict standing in for the OS keychain -- keyring.
    set_password/get_password/delete_password all patched onto the same
    store, scoped to placeinator.placement.auth's own module reference."""
    store: dict[tuple[str, str], str] = {}

    def set_password(service: str, username: str, value: str) -> None:
        store[(service, username)] = value

    def get_password(service: str, username: str) -> str | None:
        return store.get((service, username))

    def delete_password(service: str, username: str) -> None:
        store.pop((service, username), None)

    monkeypatch.setattr("placeinator.placement.auth.keyring.set_password", set_password)
    monkeypatch.setattr("placeinator.placement.auth.keyring.get_password", get_password)
    monkeypatch.setattr("placeinator.placement.auth.keyring.delete_password", delete_password)
    return store


@pytest.fixture
def _connected(_fake_keyring, monkeypatch):
    """Marks Gmail as connected without running the real OAuth flow --
    directly seeds the fake keychain and stubs get_credentials, which is
    all `service.sync`/`confirm_record` actually need."""
    _fake_keyring[("placeinator", "google-oauth")] = "fake-stored-credential"
    monkeypatch.setattr(
        "placeinator.placement.auth.get_credentials", lambda: _FakeCredentials()
    )


@pytest.fixture
def _mock_calendar(monkeypatch):
    """Records every call rather than hitting the real Calendar API."""
    calls: list[object] = []

    def create_event(credentials, event):
        calls.append(event)
        return f"fake-calendar-event-{len(calls)}"

    monkeypatch.setattr("placeinator.placement.calendar.create_event", create_event)
    return calls


def _mock_fetch(messages: list[FetchedMessage]):
    def fetch_new_messages(credentials, last_history_id):
        return messages, "999"

    return fetch_new_messages


@pytest.fixture
def _sidecar_env(tmp_path, monkeypatch):
    """Mirrors tests/integration/test_ats_feed_api.py's fixture: a fresh,
    migrated, per-test database with both caches reset."""
    from placeinator.db.session import reset_engine
    from placeinator.settings import get_settings

    monkeypatch.setenv("PLACEINATOR_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    reset_engine()
    upgrade_to_head()
    yield
    reset_engine()
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def client(_sidecar_env):
    token = generate_token()
    app = create_app()
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://sidecar") as c:
            c.headers["Authorization"] = f"Bearer {token}"
            yield c


async def _onboard(client) -> None:
    response = await client.put(
        "/api/profile",
        json={
            "full_name": "Jane Doe",
            "email": "jane.doe@college.edu",
            "student_id": "CS2024001",
            "preferences": {"target_roles": ["Backend Engineer"]},
        },
    )
    assert response.status_code == 200, response.text


async def test_status_reflects_the_fake_keychain(client, _fake_keyring):
    response = await client.get("/api/placement/status")
    assert response.status_code == 200
    assert response.json() == {"connected": False}


async def test_sync_without_a_connection_412s(client):
    await _onboard(client)
    response = await client.post("/api/placement/sync")
    assert response.status_code == 412, response.text


async def test_sync_without_onboarding_412s(client, _connected, monkeypatch):
    monkeypatch.setattr("placeinator.placement.gmail.fetch_new_messages", _mock_fetch([]))
    response = await client.post("/api/placement/sync")
    assert response.status_code == 412, response.text


async def test_connect_without_a_client_secret_file_412s(client):
    """No google_oauth_client.json exists under the test's tmp_path data
    dir, so connect() must raise ClientSecretNotFoundError before ever
    attempting the real interactive OAuth loopback flow."""
    response = await client.post("/api/placement/connect")
    assert response.status_code == 412, response.text


async def test_disconnect_clears_the_stored_credential(client, _fake_keyring):
    _fake_keyring[("placeinator", "google-oauth")] = "fake-stored-credential"

    response = await client.post("/api/placement/disconnect")
    assert response.status_code == 204, response.text
    assert ("placeinator", "google-oauth") not in _fake_keyring

    status_response = await client.get("/api/placement/status")
    assert status_response.json() == {"connected": False}


async def test_disconnect_when_not_connected_is_a_no_op(client, _fake_keyring):
    response = await client.post("/api/placement/disconnect")
    assert response.status_code == 204, response.text
    assert _fake_keyring == {}


async def test_a_strong_email_and_name_match_from_an_attachment_auto_accepts(
    client, _connected, _mock_calendar, monkeypatch
):
    """spec's own worked example: a shortlist sheet, one matching row,
    strong enough (email + name) to auto-accept, with a real event
    extracted and a real (mocked) calendar event created."""
    await _onboard(client)

    attachment_bytes = _xlsx_bytes(
        [
            [
                "Candidate Name",
                "Email",
                "Result",
                "Company",
                "Round",
                "Interview Date",
                "Start Time",
            ],
            [
                "Jane Doe",
                "jane.doe@college.edu",
                "Selected for interview",
                "Acme Corp",
                "Technical Interview",
                "August 25, 2026",
                "10:30 AM",
            ],
        ]
    )
    message = FetchedMessage(
        message_id="msg-1",
        subject="You have been shortlisted for the next round",
        sender="Acme Corp Careers <hr@acme.com>",
        body_text="Please find the shortlist attached.",
        attachments=(
            FetchedAttachment(
                filename="shortlist.xlsx", mime_type="application/xlsx", data=attachment_bytes
            ),
        ),
    )
    monkeypatch.setattr("placeinator.placement.gmail.fetch_new_messages", _mock_fetch([message]))

    sync_response = await client.post("/api/placement/sync")
    assert sync_response.status_code == 204, sync_response.text

    timeline = await client.get("/api/placement/timeline")
    assert timeline.status_code == 200
    body = timeline.json()
    assert "Acme Corp" in body
    record = body["Acme Corp"][0]
    assert record["status"] == "shortlisted"
    assert record["needs_review"] is False
    assert set(record["matched_on"]) == {"email", "name"}
    assert len(record["events"]) == 1
    event = record["events"][0]
    assert event["event_type"] == "technical_round"
    assert event["event_date"] == "2026-08-25"
    assert event["calendar_event_id"] == "fake-calendar-event-1"

    review_queue = await client.get("/api/placement/review-queue")
    assert review_queue.json() == []  # auto-accepted, never entered the queue

    assert len(_mock_calendar) == 1  # the calendar call actually happened


async def test_a_scanned_attachment_mentioning_the_candidate_lands_in_review(
    client, _connected, _mock_calendar, monkeypatch
):
    """OCR (placeinator.placement.ocr) is the fallback for a PDF attachment
    with no extractable table -- real ONNX inference through the real
    RapidOCR engine, not mocked, same as this file's other real-embedding
    tests. Deliberately never auto-accepted, whatever the match strength --
    see placeinator.placement.service's OCR branch."""
    await _onboard(client)

    attachment_bytes = _scanned_pdf_bytes(
        ["Placement Shortlist", "Jane Doe - SHORTLISTED", "Company: Acme Corp"]
    )
    message = FetchedMessage(
        message_id="msg-scan-1",
        subject="Shortlist results (scanned)",
        sender="hr@acme.com",
        body_text="See attached scan.",
        attachments=(
            FetchedAttachment(
                filename="shortlist_scan.pdf", mime_type="application/pdf", data=attachment_bytes
            ),
        ),
    )
    monkeypatch.setattr("placeinator.placement.gmail.fetch_new_messages", _mock_fetch([message]))

    sync_response = await client.post("/api/placement/sync")
    assert sync_response.status_code == 204, sync_response.text

    queue = (await client.get("/api/placement/review-queue")).json()
    assert len(queue) == 1
    assert queue[0]["needs_review"] is True
    assert queue[0]["matched_on"] == ["ocr_text"]
    assert len(_mock_calendar) == 0  # never auto-accepted, so no auto-created event either


async def test_a_scanned_attachment_not_mentioning_the_candidate_falls_back_to_inbox_signal(
    client, _connected, monkeypatch
):
    """When OCR doesn't turn up the candidate either, this falls all the way
    through to the pre-existing "the message landed in this connected
    mailbox" signal (service.py's own else branch, unchanged by OCR) --
    matched_on is "inbox", not "ocr_text", proving OCR correctly declined
    the match rather than silently swallowing the message."""
    await _onboard(client)

    attachment_bytes = _scanned_pdf_bytes(["Placement Shortlist", "John Smith - SHORTLISTED"])
    message = FetchedMessage(
        message_id="msg-scan-2",
        subject="Shortlist results (scanned)",
        sender="hr@acme.com",
        body_text="See attached scan.",
        attachments=(
            FetchedAttachment(
                filename="shortlist_scan.pdf", mime_type="application/pdf", data=attachment_bytes
            ),
        ),
    )
    monkeypatch.setattr("placeinator.placement.gmail.fetch_new_messages", _mock_fetch([message]))

    sync_response = await client.post("/api/placement/sync")
    assert sync_response.status_code == 204, sync_response.text

    timeline = (await client.get("/api/placement/timeline")).json()
    records = [r for group in timeline.values() for r in group]
    assert len(records) == 1
    assert records[0]["matched_on"] == ["inbox"]


async def test_a_weak_match_lands_in_the_review_queue_and_confirm_creates_the_event(
    client, _connected, _mock_calendar, monkeypatch
):
    await _onboard(client)

    attachment_bytes = _xlsx_bytes(
        [
            ["Candidate Name", "Result", "Company", "Interview Date"],
            ["Jane Doe", "Selected for interview", "Globex", "August 25, 2026"],
        ]
    )
    message = FetchedMessage(
        message_id="msg-2",
        subject="Shortlist results",
        sender="hr@globex.com",
        body_text="See attached.",
        attachments=(
            FetchedAttachment(
                filename="results.xlsx", mime_type="application/xlsx", data=attachment_bytes
            ),
        ),
    )
    monkeypatch.setattr("placeinator.placement.gmail.fetch_new_messages", _mock_fetch([message]))

    sync_response = await client.post("/api/placement/sync")
    assert sync_response.status_code == 204, sync_response.text

    queue = (await client.get("/api/placement/review-queue")).json()
    assert len(queue) == 1
    record_id = queue[0]["id"]
    assert queue[0]["needs_review"] is True
    assert len(_mock_calendar) == 0  # not created yet -- still needs review

    confirm_response = await client.post(f"/api/placement/review/{record_id}/confirm")
    assert confirm_response.status_code == 200, confirm_response.text
    assert confirm_response.json()["needs_review"] is False
    assert len(_mock_calendar) == 1  # created only now, on explicit confirmation

    empty_queue = await client.get("/api/placement/review-queue")
    assert empty_queue.json() == []


async def test_rejecting_a_review_queue_item_deletes_it(client, _connected, monkeypatch):
    await _onboard(client)

    attachment_bytes = _xlsx_bytes([["Candidate Name"], ["Jane Doe"]])
    message = FetchedMessage(
        message_id="msg-3",
        subject="Shortlist update",
        sender="hr@initech.com",
        body_text="See attached.",
        attachments=(
            FetchedAttachment(
                filename="update.xlsx", mime_type="application/xlsx", data=attachment_bytes
            ),
        ),
    )
    monkeypatch.setattr("placeinator.placement.gmail.fetch_new_messages", _mock_fetch([message]))
    await client.post("/api/placement/sync")

    queue = (await client.get("/api/placement/review-queue")).json()
    record_id = queue[0]["id"]

    reject_response = await client.post(f"/api/placement/review/{record_id}/reject")
    assert reject_response.status_code == 204, reject_response.text

    empty_queue = await client.get("/api/placement/review-queue")
    assert empty_queue.json() == []


async def test_resyncing_the_same_message_does_not_duplicate_the_event(
    client, _connected, _mock_calendar, monkeypatch
):
    """The dedupe_key unique constraint doing its actual job -- verified via
    two full syncs of the same message, not just unit-tested in isolation."""
    await _onboard(client)

    attachment_bytes = _xlsx_bytes(
        [
            ["Candidate Name", "Email", "Company", "Interview Date"],
            ["Jane Doe", "jane.doe@college.edu", "Umbrella Corp", "August 25, 2026"],
        ]
    )
    message = FetchedMessage(
        message_id="msg-4",
        subject="Shortlisted",
        sender="hr@umbrella.com",
        body_text="See attached.",
        attachments=(
            FetchedAttachment(
                filename="list.xlsx", mime_type="application/xlsx", data=attachment_bytes
            ),
        ),
    )
    monkeypatch.setattr("placeinator.placement.gmail.fetch_new_messages", _mock_fetch([message]))

    await client.post("/api/placement/sync")
    await client.post("/api/placement/sync")

    timeline = (await client.get("/api/placement/timeline")).json()
    assert len(timeline["Umbrella Corp"][0]["events"]) == 1
