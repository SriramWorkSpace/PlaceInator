"""Exercises POST /api/jobs/ats-feed through the real ASGI app and a real
SQLite database, with AtsFeedSource's network layer swapped for a mock
transport serving the same fixtures as tests/unit/test_ats_feed.py -- this
covers the route -> service -> upsert -> response-serialization path the
adapter-level unit tests don't.

model-marked: persistence goes through _apply_requirements, which calls the
real embedding model (not mocked here, unlike the network layer) -- same
reason tests/integration/test_m1_flow.py is model-marked.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from placeinator.app import create_app
from placeinator.db.migrate import upgrade_to_head
from placeinator.jobs.sources.ats_feed import AtsFeedSource
from placeinator.security import generate_token

pytestmark = [pytest.mark.model, pytest.mark.asyncio]

FIXTURES = Path(__file__).parents[1] / "fixtures" / "ats_feed"


def _load(name: str) -> dict | list:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _mock_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/robots.txt":
        return httpx.Response(404)
    if request.url.path == "/v1/boards/acme/jobs":
        return httpx.Response(200, json=_load("greenhouse_list.json"))
    if request.url.path == "/v1/boards/acme/jobs/8077887":
        return httpx.Response(200, json=_load("greenhouse_detail_8077887.json"))
    if request.url.path == "/v1/boards/acme/jobs/8023928":
        return httpx.Response(404)
    raise AssertionError(f"unexpected request: {request.url}")


@pytest.fixture
def _sidecar_env(tmp_path, monkeypatch):
    """Mirrors tests/integration/test_m1_flow.py's fixture: a fresh,
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
async def client(_sidecar_env, monkeypatch):
    # sync_ats_feed constructs `AtsFeedSource()` with no arguments, so the
    # mock transport is injected by patching the name as imported into
    # placeinator.jobs.service's namespace -- scoped to just this one call
    # site, unlike patching httpx.Client globally, which would also hijack
    # fastembed's own unrelated httpx usage (confirmed: it does, when tried).
    def mocked_source(**_kwargs: object) -> AtsFeedSource:
        mock_transport_client = httpx.Client(transport=httpx.MockTransport(_mock_handler))
        return AtsFeedSource(client=mock_transport_client)

    monkeypatch.setattr("placeinator.jobs.service.AtsFeedSource", mocked_source)

    token = generate_token()
    app = create_app()
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://sidecar") as c:
            c.headers["Authorization"] = f"Bearer {token}"
            yield c


async def test_ats_feed_endpoint_creates_jobs(client):
    response = await client.post("/api/jobs/ats-feed", json={"companies": ["greenhouse:acme"]})
    assert response.status_code == 200, response.text

    body = response.json()
    assert body["blocked_reason"] is None
    assert len(body["jobs"]) == 2
    assert body["jobs"][0]["source"] == "ats_feed"
    assert body["jobs"][0]["designation"].strip() == "Account Executive, Bridge"


async def test_ats_feed_endpoint_upserts_on_repeated_sync(client):
    first = await client.post("/api/jobs/ats-feed", json={"companies": ["greenhouse:acme"]})
    second = await client.post("/api/jobs/ats-feed", json={"companies": ["greenhouse:acme"]})
    assert first.status_code == second.status_code == 200

    all_jobs = await client.get("/api/jobs")
    # Not 4 -- syncing the same company twice must update in place, not
    # duplicate, since both calls return the same two source_refs.
    assert len(all_jobs.json()) == 2


async def test_ats_feed_endpoint_rejects_malformed_company_entry(client):
    response = await client.post("/api/jobs/ats-feed", json={"companies": ["not-valid"]})
    assert response.status_code == 422


async def test_ats_feed_endpoint_rejects_empty_companies_list(client):
    response = await client.post("/api/jobs/ats-feed", json={"companies": []})
    assert response.status_code == 422
