"""FastAPI application factory for the sidecar."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from placeinator.api import (
    career,
    health,
    jobs,
    latex,
    matching,
    outreach,
    placement,
    profile,
    resumes,
)
from placeinator.db.migrate import upgrade_to_head
from placeinator.matching.vectors import ModelDownloadError, warm_up_model
from placeinator.security import require_token
from placeinator.settings import get_settings

log = logging.getLogger("placeinator")


def _warm_up_embedding_model() -> None:
    """Best-effort: get the model loading (or downloading, on a genuine
    first run) before the user's first resume upload needs it, rather than
    stalling that request. A failure here isn't fatal and isn't reported --
    _model() isn't cached on failure (lru_cache never caches an exception),
    so the same attempt happens again and surfaces properly as a 503 via the
    ModelDownloadError handler below, the moment a real request actually
    needs it.

    The PDF engine (placeinator.latex.compile) deliberately does NOT get the
    same startup warm-up: unlike the embedding model, which nearly every
    feature touches, Tectonic is needed only by the PDF-export endpoint, and
    warming it up unconditionally at every app startup would mean every
    integration test that spins up the real app -- not just the LaTeX ones --
    pays a real network cost for a capability it never uses. It stays purely
    lazy, downloaded on the first actual /api/latex/tailor/pdf call."""
    try:
        warm_up_model()
    except ModelDownloadError:
        log.warning("embedding model warm-up failed; will retry on first real use")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.ensure_dirs()

    # Alembic is the only thing that ever creates or alters schema. Calling
    # create_all as well would let a fresh install diverge from a migrated one
    # and leave alembic_version empty, so the first real migration would try to
    # build tables that already exist.
    upgrade_to_head()

    # Scheduled as a task, not awaited -- awaiting asyncio.to_thread directly
    # would block the handshake on a multi-second (or, offline, much longer)
    # model load. This must not slow down startup the way it would if it ran
    # inline.
    #
    # The task object itself must be kept referenced somewhere for its whole
    # lifetime -- asyncio only holds a weak reference internally, so an
    # unreferenced task can be garbage-collected mid-run. app.state is this
    # object's home for exactly that reason.
    app.state.model_warm_up_task = asyncio.create_task(asyncio.to_thread(_warm_up_embedding_model))

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
    app.include_router(profile.router, dependencies=[protected])
    app.include_router(resumes.router, dependencies=[protected])
    app.include_router(jobs.router, dependencies=[protected])
    app.include_router(matching.router, dependencies=[protected])
    app.include_router(latex.router, dependencies=[protected])
    app.include_router(placement.router, dependencies=[protected])
    app.include_router(career.router, dependencies=[protected])
    app.include_router(outreach.router, dependencies=[protected])

    # One handler for every route that touches embeddings (resumes, jobs,
    # latex, career, outreach all end up calling into matching.vectors) --
    # a network failure during the model's first-run download must surface
    # as a clean 503, not a raw traceback, without scattering try/except
    # across each of those modules individually.
    @app.exception_handler(ModelDownloadError)
    async def handle_model_download_error(
        _request: Request, exc: ModelDownloadError
    ) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    return app
