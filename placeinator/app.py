"""FastAPI application factory for the sidecar."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from placeinator.api import health
from placeinator.db.migrate import upgrade_to_head
from placeinator.security import require_token
from placeinator.settings import get_settings

log = logging.getLogger("placeinator")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.ensure_dirs()

    # Alembic is the only thing that ever creates or alters schema. Calling
    # create_all as well would let a fresh install diverge from a migrated one
    # and leave alembic_version empty, so the first real migration would try to
    # build tables that already exist.
    upgrade_to_head()

    log.info("sidecar ready, data dir: %s", settings.data_dir)
    yield


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="PlaceInator Core",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.dev_mode else None,
        openapi_url="/openapi.json",
    )

    # The WebView serves the UI from a tauri:// or localhost:1420 origin, so the
    # loopback API needs CORS even though both sides are local.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # /health is deliberately unauthenticated: the shell polls it to know when
    # the sidecar is up, before it has anything to authenticate with.
    app.include_router(health.router)

    # Everything else requires the handshake token.
    protected = Depends(require_token)
    app.include_router(health.protected_router, dependencies=[protected])

    return app
