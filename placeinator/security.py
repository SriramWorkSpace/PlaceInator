"""Bearer-token auth for the loopback API.

The sidecar listens on 127.0.0.1 only, but a loopback port is reachable by any
local process, so every request must still carry the token handed to the shell
over the startup handshake.
"""

from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, status

_TOKEN: str = ""


def generate_token() -> str:
    global _TOKEN
    _TOKEN = secrets.token_urlsafe(32)
    return _TOKEN


def get_token() -> str:
    return _TOKEN


async def require_token(authorization: str = Header(default="")) -> None:
    """FastAPI dependency: reject any request without the handshake token."""
    expected = get_token()
    if not expected:  # token not yet generated; refuse rather than allow
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "sidecar not ready")

    scheme, _, supplied = authorization.partition(" ")
    if scheme.lower() != "bearer" or not secrets.compare_digest(supplied, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or missing token")
