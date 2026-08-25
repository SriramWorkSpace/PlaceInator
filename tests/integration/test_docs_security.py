"""Regression coverage for the auto-generated docs routes.

FastAPI attaches `/docs`, `/redoc`, and `/openapi.json` directly to the
`FastAPI(...)` app instance, not to any `APIRouter` -- so the
`dependencies=[protected]` mechanism applied to every feature router in
`create_app()` never reaches them. `docs_url` was already gated on
`settings.dev_mode`; `redoc_url` and `openapi_url` were not, which let any
local process read the full API schema (and, in dev builds, browse it
interactively) with no token at all, in every build including packaged
production ones. This pins the fix: all three routes are None outside dev
mode, and only `/health` stays reachable without a token in that state.

No real embedding model is needed here -- the lifespan warm-up runs as a
background task and its failure is caught internally, so this stays
unmarked (default `pytest tests/ -q`) rather than `model`-marked.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from placeinator.app import create_app
from placeinator.db.migrate import upgrade_to_head
from placeinator.security import generate_token
from placeinator.settings import get_settings

pytestmark = [pytest.mark.asyncio]


@pytest.fixture
def _sidecar_env(tmp_path, monkeypatch):
    from placeinator.db.session import reset_engine

    monkeypatch.setenv("PLACEINATOR_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    reset_engine()
    upgrade_to_head()
    yield
    reset_engine()
    get_settings.cache_clear()


async def _make_client(_sidecar_env) -> AsyncClient:
    app = create_app()
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://sidecar")


async def test_docs_routes_are_disabled_outside_dev_mode(_sidecar_env, monkeypatch):
    monkeypatch.setenv("PLACEINATOR_DEV_MODE", "false")
    get_settings.cache_clear()

    async with await _make_client(_sidecar_env) as client:
        for path in ("/docs", "/redoc", "/openapi.json"):
            response = await client.get(path)
            assert response.status_code == 404, path


async def test_health_is_still_reachable_without_a_token_outside_dev_mode(
    _sidecar_env, monkeypatch
):
    monkeypatch.setenv("PLACEINATOR_DEV_MODE", "false")
    get_settings.cache_clear()

    async with await _make_client(_sidecar_env) as client:
        response = await client.get("/health")
        assert response.status_code == 200


async def test_protected_routes_still_require_a_token_outside_dev_mode(
    _sidecar_env, monkeypatch
):
    monkeypatch.setenv("PLACEINATOR_DEV_MODE", "false")
    get_settings.cache_clear()
    generate_token()

    async with await _make_client(_sidecar_env) as client:
        response = await client.get("/api/status")
        assert response.status_code == 401


async def test_docs_routes_are_available_in_dev_mode(_sidecar_env, monkeypatch):
    monkeypatch.setenv("PLACEINATOR_DEV_MODE", "true")
    get_settings.cache_clear()

    async with await _make_client(_sidecar_env) as client:
        assert (await client.get("/docs")).status_code == 200
        assert (await client.get("/redoc")).status_code == 200
        assert (await client.get("/openapi.json")).status_code == 200
