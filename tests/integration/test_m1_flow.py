"""End-to-end proof of the M1 acceptance bar (docs/roadmap.md): onboard, add
resumes, paste a JD, get a ranked recommendation with a readable explanation.

Runs the real ASGI app (in-process, via httpx.ASGITransport -- no subprocess
needed here since, unlike test_handshake.py, nothing about stdout matters) with
a temp SQLite database and the real embedding model, so it is model-marked and
opt-in like tests/integration/test_scoring.py.
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

DESIGN_RESUME_TEX = rb"""
\documentclass{article}
\begin{document}

John Smith

\section{Skills}
Figma, Photoshop, Illustrator

\section{Experience}
\begin{itemize}
\item Designed marketing graphics for a retail brand
\end{itemize}

\section{Projects}
\begin{itemize}
\item Redesigned a brand's visual identity
\end{itemize}

\end{document}
"""

JOB_DESCRIPTION = """\
Backend Engineer

Requirements
- Required: strong experience with Python
- Required: experience with FastAPI or a similar framework

Responsibilities
- You will design and operate backend REST services
- You will deploy services to Kubernetes
"""


@pytest.fixture
def _sidecar_env(tmp_path, monkeypatch):
    """A fresh, migrated, per-test database -- mirrors what main.py does on
    real startup, minus the subprocess and the socket handshake.

    Both caches (Settings and the SQLAlchemy engine) must be cleared, or a
    later test silently reuses an earlier test's SQLite file instead of its
    own tmp_path -- see placeinator.db.session.reset_engine.
    """
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
    # main.py normally calls this before serving, as part of the startup
    # handshake; the test drives the ASGI app directly, so it must do the
    # same or every request 503s with "sidecar not ready".
    token = generate_token()
    app = create_app()
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://sidecar") as c:
            c.headers["Authorization"] = f"Bearer {token}"
            yield c


async def test_m1_add_resumes_paste_jd_get_ranked_recommendation(client):
    onboarding = await client.put(
        "/api/profile",
        json={
            "full_name": "Jane Doe",
            "email": "jane@example.com",
            "preferences": {"target_roles": ["Backend Engineer"]},
        },
    )
    assert onboarding.status_code == 200
    assert onboarding.json()["onboarded"] is True

    sde_upload = await client.post(
        "/api/resumes",
        data={"label": "SDE Resume", "source_format": "tex", "target_role": "Backend Engineer"},
        files={"file": ("sde.tex", SDE_RESUME_TEX, "text/x-tex")},
    )
    assert sde_upload.status_code == 201, sde_upload.text
    assert sde_upload.json()["chunk_count"] > 0

    design_upload = await client.post(
        "/api/resumes",
        data={"label": "Design Resume", "source_format": "tex", "target_role": "Graphic Designer"},
        files={"file": ("design.tex", DESIGN_RESUME_TEX, "text/x-tex")},
    )
    assert design_upload.status_code == 201, design_upload.text

    resumes = await client.get("/api/resumes")
    assert len(resumes.json()) == 2

    job = await client.post(
        "/api/jobs/manual",
        json={
            "company": "Acme",
            "designation": "Backend Engineer",
            "description": JOB_DESCRIPTION,
        },
    )
    assert job.status_code == 201, job.text
    job_id = job.json()["id"]
    assert "python" in job.json()["required_skill_ids"]

    ranked = await client.post(f"/api/matching/jobs/{job_id}/rank-resumes")
    assert ranked.status_code == 200, ranked.text
    results = ranked.json()

    assert len(results) == 2
    assert results[0]["resume_label"] == "SDE Resume"
    assert results[0]["personalized_score"] > results[1]["personalized_score"]

    explanation = results[0]["explanation"]
    assert set(explanation) == {"overall", "skills", "projects", "experience", "role"}
    assert explanation["skills"]["value"] > 0


async def test_ranking_requires_onboarding_first(client):
    response = await client.post("/api/matching/jobs/1/rank-resumes")
    assert response.status_code == 412


async def test_resume_upload_requires_onboarding_first(client):
    response = await client.post(
        "/api/resumes",
        data={"label": "X", "source_format": "tex"},
        files={"file": ("x.tex", b"\\section{Skills}\nPython", "text/x-tex")},
    )
    assert response.status_code == 412
