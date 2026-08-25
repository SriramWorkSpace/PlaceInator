"""Regression coverage for GET /api/matching/model-status -- polled by the
frontend's first-run download banner (AppShell), but never covered at the
API layer before this: the underlying get_model_download_status() has unit
coverage, but the route's response model, auth requirement, and wiring did
not.

No real embedding model needed: the route is DB-free and reads bytes off
disk against Settings.models_dir, which starts empty in a fresh tmp_path
data dir -- exactly the "not ready" state this pins.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from placeinator.app import create_app
from placeinator.db.migrate import upgrade_to_head
from placeinator.security import generate_token

pytestmark = [pytest.mark.asyncio]


@pytest.fixture
def _sidecar_env(tmp_path, monkeypatch):
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
    # Deliberately skips app.router.lifespan_context(app): that would kick
    # off the real background embedding-model warm-up (placeinator/app.py's
    # lifespan), which would race with -- and, once it completes, silently
    # pollute -- the process-wide _model() lru_cache these tests assert
    # against. upgrade_to_head() in _sidecar_env already covers the only
    # other thing lifespan would have done.
    token = generate_token()
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://sidecar") as c:
        c.headers["Authorization"] = f"Bearer {token}"
        yield c


async def test_model_status_reports_not_ready_against_an_empty_models_dir(client):
    response = await client.get("/api/matching/model-status")
    assert response.status_code == 200, response.text
    assert response.json() == {"ready": False, "downloading": False, "approx_progress": 0.0}


async def test_model_status_requires_a_token(_sidecar_env):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://sidecar") as c:
        response = await c.get("/api/matching/model-status")
    assert response.status_code in (401, 503)
