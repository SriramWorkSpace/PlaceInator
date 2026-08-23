"""Exercises POST /api/latex/tailor through the real ASGI app, a real SQLite
database, and the real embedding model -- the full pipeline from an uploaded
.tex resume through to a tailored, re-parseable .tex output.

model-marked for the same reason as test_m1_flow.py: resume upload chunks and
embeds through the real model, and tailor_resume scores against those real
persisted vectors (see placeinator.latex.tailoring's module docstring).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from placeinator.app import create_app
from placeinator.db.migrate import upgrade_to_head
from placeinator.latex.parsing import parse_latex
from placeinator.security import generate_token

pytestmark = [pytest.mark.model, pytest.mark.asyncio]

FIXTURES = Path(__file__).parents[1] / "fixtures" / "resumes"
SDE_RESUME_TEX = (FIXTURES / "sde_resume.tex").read_bytes()

JOB_DESCRIPTION = """\
Backend Engineer

Requirements
- Required: strong experience with Python and FastAPI
- Required: experience with Kubernetes and Docker

Responsibilities
- You will design and ship REST APIs
- You will deploy services to Kubernetes
"""


@pytest.fixture
def _sidecar_env(tmp_path, monkeypatch):
    """Mirrors tests/integration/test_m1_flow.py's fixture: a fresh, migrated,
    per-test database with both caches reset."""
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


async def _onboard_and_seed(client) -> tuple[int, int]:
    """Returns (resume_id, job_id) for a real, chunked-and-embedded resume
    and a real, requirement-extracted job."""
    onboarding = await client.put(
        "/api/profile",
        json={"full_name": "Jane Doe", "email": "jane@example.com"},
    )
    assert onboarding.status_code == 200, onboarding.text

    upload = await client.post(
        "/api/resumes",
        data={"label": "SDE Resume", "source_format": "tex", "target_role": "Backend Engineer"},
        files={"file": ("sde.tex", SDE_RESUME_TEX, "text/x-tex")},
    )
    assert upload.status_code == 201, upload.text
    resume_id = upload.json()["id"]

    job = await client.post(
        "/api/jobs/manual",
        json={"company": "Acme", "designation": "Backend Engineer", "description": JOB_DESCRIPTION},
    )
    assert job.status_code == 201, job.text
    return resume_id, job.json()["id"]


async def test_tailor_endpoint_returns_a_reordered_reparseable_tex(client):
    resume_id, job_id = await _onboard_and_seed(client)

    response = await client.post(
        "/api/latex/tailor", json={"resume_id": resume_id, "job_id": job_id}
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["tex"]
    # The emitted .tex must still be valid LaTeX -- splicing must not corrupt
    # structure.
    reparsed = parse_latex(body["tex"])
    assert [s.heading for s in reparsed.sections] == ["Skills", "Experience", "Projects"]

    assert {s["heading"] for s in body["sections"]} == {"Skills", "Experience", "Projects"}
    assert "python" in body["requirements_matched"]


async def test_repeated_tailor_calls_upsert_not_duplicate(client):
    resume_id, job_id = await _onboard_and_seed(client)

    first = await client.post("/api/latex/tailor", json={"resume_id": resume_id, "job_id": job_id})
    second = await client.post("/api/latex/tailor", json={"resume_id": resume_id, "job_id": job_id})

    assert first.status_code == second.status_code == 200


async def test_excluding_a_bullet_removes_it_from_the_response(client):
    resume_id, job_id = await _onboard_and_seed(client)

    first = await client.post("/api/latex/tailor", json={"resume_id": resume_id, "job_id": job_id})
    experience = next(s for s in first.json()["sections"] if s["heading"] == "Experience")
    bullet_to_exclude = experience["bullets"][0]["bullet_id"]

    second = await client.post(
        "/api/latex/tailor",
        json={
            "resume_id": resume_id,
            "job_id": job_id,
            "excluded_bullet_ids": [bullet_to_exclude],
        },
    )
    assert second.status_code == 200, second.text
    excluded_text = next(
        b["text"]
        for s in first.json()["sections"]
        if s["heading"] == "Experience"
        for b in s["bullets"]
        if b["bullet_id"] == bullet_to_exclude
    )
    assert excluded_text not in second.json()["tex"]


async def test_unknown_resume_id_404s(client):
    _resume_id, job_id = await _onboard_and_seed(client)

    response = await client.post("/api/latex/tailor", json={"resume_id": 999999, "job_id": job_id})
    assert response.status_code == 404


async def test_unknown_job_id_404s(client):
    resume_id, _job_id = await _onboard_and_seed(client)

    response = await client.post(
        "/api/latex/tailor", json={"resume_id": resume_id, "job_id": 999999}
    )
    assert response.status_code == 404


async def test_malformed_latex_source_422s_instead_of_500(client):
    onboarding = await client.put(
        "/api/profile", json={"full_name": "Jane Doe", "email": "jane@example.com"}
    )
    assert onboarding.status_code == 200

    broken = b"\\documentclass{article}\n\\begin{document}\n\\section{Skills\nno closing brace\n"
    upload = await client.post(
        "/api/resumes",
        data={"label": "Broken", "source_format": "tex"},
        files={"file": ("broken.tex", broken, "text/x-tex")},
    )
    assert upload.status_code == 201, upload.text  # upload/chunking never parses LaTeX structure
    resume_id = upload.json()["id"]

    job = await client.post(
        "/api/jobs/manual",
        json={"company": "Acme", "designation": "Backend Engineer", "description": JOB_DESCRIPTION},
    )
    job_id = job.json()["id"]

    response = await client.post(
        "/api/latex/tailor", json={"resume_id": resume_id, "job_id": job_id}
    )
    assert response.status_code == 422


@pytest.mark.tex
async def test_tailor_pdf_endpoint_returns_a_real_pdf(client):
    """Manual-only (see pyproject.toml's `tex` marker): compiles through the
    real bundled Tectonic engine, not a mock. The first run on a machine
    also pays Tectonic's own one-time format-bootstrap cost (several minutes
    on a slow connection, see placeinator/latex/compile.py) -- run this
    directly (`pytest tests/ -m tex -v`) rather than as part of the normal
    suite."""
    resume_id, job_id = await _onboard_and_seed(client)

    response = await client.post(
        "/api/latex/tailor/pdf", json={"resume_id": resume_id, "job_id": job_id}
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF-")
