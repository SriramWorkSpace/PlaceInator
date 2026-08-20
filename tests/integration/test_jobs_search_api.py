"""Exercises POST /api/jobs/search through the real ASGI app and a real
SQLite database, with IndeedSource's network layer swapped for a mock
transport serving the same captured fixture as tests/unit/test_indeed.py.

This covers the route -> service -> upsert -> response-serialization path
that the adapter-level unit tests don't. It is the path behind the Jobs
page's job-board search form -- the only discovery control wired into the UI
-- and it had no end-to-end coverage at all before this file.

model-marked for the same reason as test_ats_feed_api.py: persistence goes
through _apply_requirements, which calls the real embedding model.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from placeinator.app import create_app
from placeinator.db.migrate import upgrade_to_head
from placeinator.jobs.sources.indeed import IndeedSource
from placeinator.security import generate_token

pytestmark = [pytest.mark.model, pytest.mark.asyncio]

FIXTURES = Path(__file__).parents[1] / "fixtures" / "indeed"


def _mock_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/robots.txt":
        return httpx.Response(200, text=(FIXTURES / "robots.txt").read_text(encoding="utf-8"))
    if request.url.path == "/jobs":
        return httpx.Response(
            200, text=(FIXTURES / "search_results.html").read_text(encoding="utf-8")
        )
    raise AssertionError(f"unexpected request: {request.url}")


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
async def client(_sidecar_env, monkeypatch):
    # search_jobs looks the adapter class up in _SEARCH_SOURCES and constructs
    # it with no arguments, so the mock transport is injected by replacing the
    # entry in that table -- scoped to this one call site, rather than patching
    # httpx.Client globally (which would also hijack fastembed's own usage).
    def mocked_source(**_kwargs: object) -> IndeedSource:
        return IndeedSource(client=httpx.Client(transport=httpx.MockTransport(_mock_handler)))

    from placeinator.db.enums import SourceKind

    monkeypatch.setattr(
        "placeinator.jobs.service._SEARCH_SOURCES",
        {SourceKind.INDEED: mocked_source},
    )

    token = generate_token()
    app = create_app()
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://sidecar") as c:
            c.headers["Authorization"] = f"Bearer {token}"
            yield c


async def test_search_endpoint_creates_jobs(client):
    response = await client.post(
        "/api/jobs/search", json={"source": "indeed", "keywords": "backend engineer"}
    )
    assert response.status_code == 200, response.text

    body = response.json()
    assert body["blocked_reason"] is None
    assert len(body["jobs"]) > 0
    assert body["jobs"][0]["source"] == "indeed"


async def test_discovered_jobs_carry_a_url_the_ui_can_link_to(client):
    """JobOut omitted `url` until this milestone, which made every discovered
    posting a dead end in the UI."""
    response = await client.post(
        "/api/jobs/search", json={"source": "indeed", "keywords": "backend engineer"}
    )

    urls = [job["url"] for job in response.json()["jobs"]]
    assert any(url and url.startswith("http") for url in urls)


async def test_repeated_search_upserts_rather_than_duplicating(client):
    first = await client.post(
        "/api/jobs/search", json={"source": "indeed", "keywords": "backend engineer"}
    )
    await client.post(
        "/api/jobs/search", json={"source": "indeed", "keywords": "backend engineer"}
    )

    created = len(first.json()["jobs"])
    all_jobs = await client.get("/api/jobs")
    # Same source_refs both times, so the second search must update in place.
    assert len(all_jobs.json()) == created


async def test_a_blocked_source_reports_a_reason_instead_of_failing(client, monkeypatch):
    """ADR 0003 end to end: linkedin is blocked by its own robots.txt, and the
    endpoint must still answer 200 with a reason the UI can show, not 5xx."""

    def blocked_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /\n")
        raise AssertionError("must not fetch when robots.txt disallows everything")

    from placeinator.db.enums import SourceKind
    from placeinator.jobs.sources.linkedin import LinkedInSource

    monkeypatch.setattr(
        "placeinator.jobs.service._SEARCH_SOURCES",
        {
            SourceKind.LINKEDIN: lambda **_k: LinkedInSource(
                client=httpx.Client(transport=httpx.MockTransport(blocked_handler))
            )
        },
    )

    response = await client.post(
        "/api/jobs/search", json={"source": "linkedin", "keywords": "backend engineer"}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["jobs"] == []
    assert body["blocked_reason"]


async def test_an_unsearchable_source_is_rejected_by_the_schema(client):
    """manual/ats_feed aren't keyword-searchable; the Literal guard must
    reject them at the edge rather than letting the service raise."""
    response = await client.post(
        "/api/jobs/search", json={"source": "manual", "keywords": "backend engineer"}
    )
    assert response.status_code == 422
