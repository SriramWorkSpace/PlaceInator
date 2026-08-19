"""Liveness and readiness endpoints.

`/health` is intentionally open so the Rust shell can poll for startup before it
has authenticated; `/api/status` is behind the token and proves the full
shell -> token -> sidecar -> database path works end to end.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from placeinator.db.session import get_engine, session_scope
from placeinator.settings import get_settings

router = APIRouter(tags=["health"])
protected_router = APIRouter(prefix="/api", tags=["health"])


class Health(BaseModel):
    status: str
    version: str


class Status(BaseModel):
    status: str
    version: str
    data_dir: str
    database_ok: bool
    table_count: int


@router.get("/health", response_model=Health)
async def health() -> Health:
    return Health(status="ok", version="0.1.0")


@protected_router.get("/status", response_model=Status)
async def status() -> Status:
    settings = get_settings()

    database_ok = False
    table_count = 0
    try:
        with session_scope() as session:
            row = session.execute(
                text("SELECT count(*) FROM sqlite_master WHERE type = 'table'")
            ).scalar_one()
            table_count = int(row)
            database_ok = True
    except Exception:  # surfaced to the UI as a degraded state, not a crash
        database_ok = False

    get_engine()
    return Status(
        status="ok",
        version="0.1.0",
        data_dir=str(settings.data_dir),
        database_ok=database_ok,
        table_count=table_count,
    )
