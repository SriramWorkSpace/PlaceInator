"""Google OAuth (Gmail + Calendar), loopback flow, OS-keychain token storage.

The refresh token never touches SQLite or a plain file -- it's stored via
`keyring` (Windows Credential Manager / macOS Keychain / Linux Secret
Service), confirmed against the real backend on this machine before this
module was written. `architecture.md`'s system diagram places "OAuth token
storage (OS keychain)" in the Tauri shell's box, but Python has its own
direct keychain bindings, so none of this needs a round trip through Rust.

The OAuth client itself (`google_oauth_client.json`, a "Desktop app" /
`"installed"`-type credential, confirmed against the real downloaded file
before this module was written) is a one-time manual setup step -- it lives
in `Settings.data_dir`, never in the repo, and identifies the *application*,
not the user. Nothing in this module can create it.
"""

from __future__ import annotations

import json
from pathlib import Path

import keyring
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from placeinator.settings import get_settings

# Least-privilege: event creation only, not full calendar control; read-only
# on Gmail, since this app never sends or modifies email.
SCOPES = (
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.events",
)

_KEYRING_SERVICE = "placeinator"
_KEYRING_USERNAME = "google-oauth"
_CLIENT_SECRET_FILENAME = "google_oauth_client.json"


class ClientSecretNotFoundError(ValueError):
    """The OAuth *application* credential (google_oauth_client.json) hasn't
    been placed in the data dir yet -- a one-time manual setup step, not
    something this module can do on its own."""


class GmailNotConnectedError(ValueError):
    """No stored user credential -- `connect()` hasn't been completed, or
    `disconnect()` was called since."""


def client_secret_path() -> Path:
    return get_settings().data_dir / _CLIENT_SECRET_FILENAME


def is_connected() -> bool:
    """Whether a user credential is stored. The single source of truth is
    the keyring entry itself -- deliberately no DB flag to keep in sync."""
    return keyring.get_password(_KEYRING_SERVICE, _KEYRING_USERNAME) is not None


def connect() -> None:
    """Runs the interactive loopback OAuth flow: opens the user's browser,
    waits for them to approve, then stores the resulting credential.

    Blocking -- `run_local_server` drives the whole exchange itself,
    including opening the browser and running a temporary local HTTP server
    to catch the redirect. Callers on an async request path should run this
    via `asyncio.to_thread` rather than await it directly.
    """
    path = client_secret_path()
    if not path.exists():
        raise ClientSecretNotFoundError(
            f"no OAuth client credential at {path} -- set up a Google Cloud "
            "OAuth client (Desktop app type) and place the downloaded JSON there"
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(path), list(SCOPES))
    credentials = flow.run_local_server(port=0)
    keyring.set_password(_KEYRING_SERVICE, _KEYRING_USERNAME, credentials.to_json())


def disconnect() -> None:
    if is_connected():
        keyring.delete_password(_KEYRING_SERVICE, _KEYRING_USERNAME)


def get_credentials() -> Credentials:
    """The stored credential, refreshed if its access token has expired.

    A refresh rotates the access token (and re-stores it -- the refresh
    token itself is long-lived and usually unchanged, but re-persisting the
    whole credential is simpler and cheaper than tracking which fields
    actually changed).
    """
    stored = keyring.get_password(_KEYRING_SERVICE, _KEYRING_USERNAME)
    if stored is None:
        raise GmailNotConnectedError("Gmail is not connected -- call connect() first")

    credentials = Credentials.from_authorized_user_info(json.loads(stored))

    if credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(Request())
        except RefreshError as exc:
            # The user revoked access, or the refresh token expired outright
            # -- neither is recoverable without re-running connect().
            keyring.delete_password(_KEYRING_SERVICE, _KEYRING_USERNAME)
            raise GmailNotConnectedError(
                f"stored Gmail credential is no longer valid: {exc}"
            ) from exc
        keyring.set_password(_KEYRING_SERVICE, _KEYRING_USERNAME, credentials.to_json())

    return credentials
