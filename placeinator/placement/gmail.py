"""Incremental Gmail fetch via the History API (spec §7, roadmap M4).

`history.list` only works going forward from a known cursor, so a fresh
connection (or a cursor Gmail no longer retains -- mailbox history isn't kept
forever) falls back to a bounded initial `messages.list` scan instead of
raising. Either path ends by recording the mailbox's current `historyId` as
the new cursor (`Preferences.gmail_last_history_id`), so the next sync picks
up from there.

Read-only throughout (`gmail.readonly` scope) -- this module never sends,
labels, or deletes anything.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# A generous but bounded initial scan -- the spec asks for placement-related
# communications, not a full mailbox import, and an unbounded scan on first
# connect would be slow and mostly irrelevant on an established inbox.
_INITIAL_SCAN_MAX_RESULTS = 200


@dataclass(frozen=True)
class FetchedAttachment:
    filename: str
    mime_type: str
    data: bytes


@dataclass(frozen=True)
class FetchedMessage:
    message_id: str
    subject: str
    sender: str
    body_text: str
    attachments: tuple[FetchedAttachment, ...]


def _service(credentials: Credentials):
    # cache_discovery=False: the discovery doc ships in the package itself
    # (confirmed on disk before this module was written), so there is
    # nothing to cache -- and googleapiclient's default file-based discovery
    # cache is a known source of stale-permission warnings in frozen/
    # read-only install layouts, worth avoiding now rather than debugging
    # once this is running from a packaged build.
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def _decode(data: str) -> bytes:
    """Gmail's body/attachment payloads are URL-safe base64, sometimes
    without the trailing `=` padding Python's decoder requires."""
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded)


def _header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def _walk_parts(
    message_id: str,
    service,
    part: dict,
    body_chunks: list[str],
    attachments: list[FetchedAttachment],
) -> None:
    """Recurses through a message's MIME tree. Plain-text parts are
    collected as body text; anything with a filename is an attachment,
    fetched via a second API call when Gmail didn't inline its data."""
    mime_type = part.get("mimeType", "")
    filename = part.get("filename", "")
    body = part.get("body", {})

    if filename:
        attachment_id = body.get("attachmentId")
        if attachment_id:
            raw = (
                service.users()
                .messages()
                .attachments()
                .get(userId="me", messageId=message_id, id=attachment_id)
                .execute()
            )
            data = _decode(raw["data"])
        elif "data" in body:
            data = _decode(body["data"])
        else:
            data = b""
        attachments.append(FetchedAttachment(filename=filename, mime_type=mime_type, data=data))
    elif mime_type == "text/plain" and "data" in body:
        body_chunks.append(_decode(body["data"]).decode("utf-8", errors="replace"))

    for child in part.get("parts", []):
        _walk_parts(message_id, service, child, body_chunks, attachments)


def _hydrate(service, message_ids: list[str]) -> list[FetchedMessage]:
    messages = []
    for message_id in message_ids:
        raw = service.users().messages().get(userId="me", id=message_id, format="full").execute()
        payload = raw["payload"]
        headers = payload.get("headers", [])

        body_chunks: list[str] = []
        attachments: list[FetchedAttachment] = []
        _walk_parts(message_id, service, payload, body_chunks, attachments)

        messages.append(
            FetchedMessage(
                message_id=message_id,
                subject=_header(headers, "Subject"),
                sender=_header(headers, "From"),
                body_text="\n".join(body_chunks),
                attachments=tuple(attachments),
            )
        )
    return messages


def _initial_scan(service) -> list[str]:
    response = (
        service.users()
        .messages()
        .list(userId="me", labelIds=["INBOX"], maxResults=_INITIAL_SCAN_MAX_RESULTS)
        .execute()
    )
    return [m["id"] for m in response.get("messages", [])]


def _incremental_scan(service, last_history_id: str) -> list[str]:
    message_ids: list[str] = []
    page_token: str | None = None
    while True:
        response = (
            service.users()
            .history()
            .list(
                userId="me",
                startHistoryId=last_history_id,
                historyTypes=["messageAdded"],
                pageToken=page_token,
            )
            .execute()
        )
        for entry in response.get("history", []):
            for added in entry.get("messagesAdded", []):
                message_ids.append(added["message"]["id"])
        page_token = response.get("nextPageToken")
        if not page_token:
            return message_ids


def fetch_new_messages(
    credentials: Credentials, last_history_id: str | None
) -> tuple[list[FetchedMessage], str]:
    """Returns (new messages since the last sync, the mailbox's current
    historyId to persist as the next cursor)."""
    service = _service(credentials)

    if last_history_id is not None:
        try:
            message_ids = _incremental_scan(service, last_history_id)
        except HttpError as exc:
            if exc.resp.status != 404:
                raise
            # Gmail no longer retains history back to this cursor -- fall
            # back to a fresh bounded scan rather than failing the sync.
            message_ids = _initial_scan(service)
    else:
        message_ids = _initial_scan(service)

    current_history_id = str(service.users().getProfile(userId="me").execute()["historyId"])
    return _hydrate(service, message_ids), current_history_id
