"""End-to-end proof of M5 (Career Intelligence and Outreach): a real
onboarded profile with a real resume and a real job produces real,
evidence-backed skill gaps and a real outreach draft that cites actual
resume text -- never a fabricated claim.

Runs the real ASGI app with a temp SQLite database and the real embedding
model (career/outreach both read MatchResult, which needs it), so this is
model-marked and opt-in, mirroring tests/integration/test_m1_flow.py.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from placeinator.app import create_app
from placeinator.db.migrate import upgrade_to_head
from placeinator.security import generate_token

pytestmark = [pytest.mark.model, pytest.mark.asyncio]

SDE_RESUME_TEX = rb"""
\documentclass{article}
\begin{document}

Jane Doe

\section{Skills}
Python, FastAPI, PostgreSQL, Docker, Kubernetes

\section{Experience}
\begin{itemize}
\item Built a backend service in Python and FastAPI handling 10k requests/sec
\item Deployed services to Kubernetes and ran CI/CD pipelines
\end{itemize}

\section{Projects}
\begin{itemize}
\item REST API for a payments platform using FastAPI and PostgreSQL
\end{itemize}

\end{document}
"""

JOB_DESCRIPTION = """\
Backend Engineer

Requirements
- Required: strong experience with Python
- Required: experience with FastAPI or a similar framework
- Required: experience with Rust

Responsibilities
- You will design and operate backend REST services
- You will deploy services to Kubernetes
"""


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


@pytest_asyncio.fixture
async def onboarded_with_resume_and_job(client):
    """Real onboarding, a real resume upload (real chunking/embedding), and
    a real job whose requirements include "rust" -- something the sample
    resume doesn't have, specifically so a skill gap actually exists to
    assert against."""
    onboarding = await client.put(
        "/api/profile",
        json={
            "full_name": "Jane Doe",
            "email": "jane@example.com",
            "preferences": {"target_roles": ["Backend Engineer"]},
        },
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
    job_id = job.json()["id"]
    assert "rust" in job.json()["required_skill_ids"]

    return client, resume_id, job_id


async def test_skill_gaps_requires_onboarding_first(client):
    response = await client.get("/api/career/skill-gaps")
    assert response.status_code == 412


async def test_a_missing_required_skill_surfaces_as_a_real_gap(onboarded_with_resume_and_job):
    client, _resume_id, job_id = onboarded_with_resume_and_job

    response = await client.get("/api/career/skill-gaps")
    assert response.status_code == 200, response.text
    gaps = response.json()

    by_id = {g["skill_id"]: g for g in gaps}
    assert "rust" in by_id, gaps
    assert "python" not in by_id  # the resume already has this -- not a gap
    evidence = by_id["rust"]["evidence"]
    assert any(e["job_id"] == job_id and e["company"] == "Acme" for e in evidence)


async def test_outreach_targets_requires_onboarding_first(client):
    response = await client.get("/api/outreach/targets")
    assert response.status_code == 412


async def test_outreach_targets_lists_the_real_job(onboarded_with_resume_and_job):
    client, _resume_id, job_id = onboarded_with_resume_and_job

    response = await client.get("/api/outreach/targets")
    assert response.status_code == 200, response.text
    targets = response.json()
    assert any(t["job"]["id"] == job_id for t in targets)


async def test_a_draft_cites_real_resume_text_not_a_fabrication(onboarded_with_resume_and_job):
    client, resume_id, job_id = onboarded_with_resume_and_job

    response = await client.post(
        "/api/outreach/drafts", json={"resume_id": resume_id, "job_id": job_id}
    )
    assert response.status_code == 200, response.text
    draft = response.json()

    assert "Acme" in draft["subject"]
    assert "Acme" in draft["body"]
    # Real bullet text from the resume, not a generated paraphrase.
    assert "10k requests/sec" in draft["body"] or "payments platform" in draft["body"]
    assert "Jane Doe" in draft["body"]


async def test_regenerating_a_draft_upserts_rather_than_duplicating(onboarded_with_resume_and_job):
    client, resume_id, job_id = onboarded_with_resume_and_job

    first = await client.post(
        "/api/outreach/drafts", json={"resume_id": resume_id, "job_id": job_id}
    )
    second = await client.post(
        "/api/outreach/drafts", json={"resume_id": resume_id, "job_id": job_id}
    )
    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]

    drafts = await client.get("/api/outreach/drafts")
    assert len(drafts.json()) == 1


async def test_deleting_a_draft_removes_it(onboarded_with_resume_and_job):
    client, resume_id, job_id = onboarded_with_resume_and_job

    created = await client.post(
        "/api/outreach/drafts", json={"resume_id": resume_id, "job_id": job_id}
    )
    draft_id = created.json()["id"]

    deleted = await client.delete(f"/api/outreach/drafts/{draft_id}")
    assert deleted.status_code == 204

    drafts = await client.get("/api/outreach/drafts")
    assert drafts.json() == []


async def test_deleting_an_unknown_draft_404s(onboarded_with_resume_and_job):
    client, _resume_id, _job_id = onboarded_with_resume_and_job
    response = await client.delete("/api/outreach/drafts/999999")
    assert response.status_code == 404
