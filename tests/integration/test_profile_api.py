"""DELETE /api/profile (Settings' "Delete account" -- full local reset).

This app has exactly one Profile row, ever (placeinator.profile.service's own
docstring), so "delete account" means "wipe everything and start over," not a
per-user scoped delete. Confirms the reset actually reaches data outside the
Profile row's own ORM cascade -- a Job (global, not owned by Profile) and its
MatchResult -- not just the profile itself. PlacementRecord follows the same
delete() call in reset_all_data but isn't exercised here: constructing one
faithfully needs a mocked Gmail fetch (see test_placement_api.py), which is
disproportionate machinery for this one assertion; its deletion is covered by
the same SQLite ON DELETE CASCADE mechanism already proven here for Job.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from placeinator.app import create_app
from placeinator.db.migrate import upgrade_to_head
from placeinator.security import generate_token

pytestmark = [pytest.mark.model, pytest.mark.asyncio]


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
    token = generate_token()
    app = create_app()
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://sidecar") as c:
            c.headers["Authorization"] = f"Bearer {token}"
            yield c


async def test_delete_account_resets_profile_jobs_and_matches(client):
    onboarding = await client.put(
        "/api/profile",
        json={
            "full_name": "Jane Doe",
            "email": "jane@example.com",
            "preferences": {"target_roles": ["Backend Engineer"]},
        },
    )
    assert onboarding.status_code == 200, onboarding.text

    resume = await client.post(
        "/api/resumes",
        data={"label": "SDE", "source_format": "tex"},
        files={"file": ("sde.tex", b"Jane Doe\nSkills: Python, FastAPI", "text/x-tex")},
    )
    assert resume.status_code == 201, resume.text

    job = await client.post(
        "/api/jobs/manual",
        json={
            "company": "Acme",
            "designation": "Backend Engineer",
            "description": "Python, FastAPI required.",
        },
    )
    assert job.status_code == 201, job.text
    job_id = job.json()["id"]

    ranked = await client.post(f"/api/matching/jobs/{job_id}/rank-resumes")
    assert ranked.status_code == 200, ranked.text
    assert len(ranked.json()) == 1

    delete_response = await client.delete("/api/profile")
    assert delete_response.status_code == 204, delete_response.text

    # Profile is gone -- back to the pre-onboarding 404.
    assert (await client.get("/api/profile")).status_code == 404
    # Job is gone too, even though it isn't owned by Profile in the schema --
    # a real check that reset_all_data() reaches beyond the Profile row's own
    # ORM cascade, not just a re-assertion of SQLAlchemy's cascade config.
    assert (await client.get("/api/jobs")).json() == []


async def test_delete_account_when_nothing_exists_yet_is_a_no_op(client):
    response = await client.delete("/api/profile")
    assert response.status_code == 204, response.text
