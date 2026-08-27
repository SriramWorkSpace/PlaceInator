"""End-to-end proof of the M1 acceptance bar (docs/roadmap.md): onboard, add
resumes, paste a JD, get a ranked recommendation with a readable explanation.

Runs the real ASGI app (in-process, via httpx.ASGITransport -- no subprocess
needed here since, unlike test_handshake.py, nothing about stdout matters) with
a temp SQLite database and the real embedding model, so it is model-marked and
opt-in like tests/integration/test_scoring.py.
"""

from __future__ import annotations

import io

import pytest
import pytest_asyncio
from docx import Document
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
    resumes_json = resumes.json()
    assert len(resumes_json) == 2
    # The first resume ever uploaded for this profile becomes primary
    # automatically; the second, uploaded without is_primary, does not.
    by_label = {r["label"]: r for r in resumes_json}
    assert by_label["SDE Resume"]["is_primary"] is True
    assert by_label["Design Resume"]["is_primary"] is False

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


async def test_extract_profile_from_resume_works_before_onboarding(client):
    """The autofill preview must not require a profile -- it runs during
    onboarding, before one exists."""
    response = await client.post(
        "/api/resumes/extract",
        data={"source_format": "tex"},
        files={"file": ("jane.tex", SDE_RESUME_TEX, "text/x-tex")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["full_name"] == "Jane Doe"


async def test_set_primary_resume_demotes_the_previous_primary(client):
    onboarding = await client.put(
        "/api/profile",
        json={"full_name": "Jane Doe", "email": "jane@example.com"},
    )
    assert onboarding.status_code == 200

    first = await client.post(
        "/api/resumes",
        data={"label": "First", "source_format": "tex"},
        files={"file": ("first.tex", SDE_RESUME_TEX, "text/x-tex")},
    )
    second = await client.post(
        "/api/resumes",
        data={"label": "Second", "source_format": "tex"},
        files={"file": ("second.tex", DESIGN_RESUME_TEX, "text/x-tex")},
    )
    assert first.json()["is_primary"] is True
    assert second.json()["is_primary"] is False

    promoted = await client.patch(f"/api/resumes/{second.json()['id']}/primary")
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["is_primary"] is True

    resumes = {r["label"]: r for r in (await client.get("/api/resumes")).json()}
    assert resumes["First"]["is_primary"] is False
    assert resumes["Second"]["is_primary"] is True


async def test_set_primary_resume_404s_for_unknown_id(client):
    onboarding = await client.put(
        "/api/profile",
        json={"full_name": "Jane Doe", "email": "jane@example.com"},
    )
    assert onboarding.status_code == 200

    response = await client.patch("/api/resumes/999999/primary")
    assert response.status_code == 404


def _docx_bytes(*lines: str) -> bytes:
    document = Document()
    for line in lines:
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


async def test_extract_job_from_file_needs_no_profile(client):
    """The JD-upload autofill preview must not require onboarding -- adding a
    job has never required a profile, and this shouldn't be an exception."""
    jd_bytes = _docx_bytes(
        "Backend Engineer",
        "",
        "Company: Acme Corp",
        "",
        "Requirements",
        "- Strong experience with Python",
    )
    response = await client.post(
        "/api/jobs/extract",
        data={"source_format": "docx"},
        files={
            "file": (
                "jd.docx",
                jd_bytes,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["designation"] == "Backend Engineer"
    assert body["company"] == "Acme Corp"
    assert "Python" in body["description"]


async def test_extract_job_from_text_needs_no_profile(client):
    """Same autofill as the file-upload path, but for text pasted directly
    into the manual-add form's textarea -- must not require onboarding."""
    response = await client.post(
        "/api/jobs/extract-text",
        json={
            "description": "Backend Engineer\n\nCompany: Acme Corp\n\n"
            "Requirements\n- Strong experience with Python"
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["designation"] == "Backend Engineer"
    assert body["company"] == "Acme Corp"
    assert "Python" in body["description"]


async def test_ranked_jobs_hard_filters_and_refilters_on_preference_change(client):
    """The relocation hard constraint is the one spec §2 rule exercisable
    through the manual-add form as it stands today (ManualJobIn has no
    salary/bond/experience fields yet) -- proves apply_hard_filters actually
    runs on create, that GET /api/jobs/ranked never hides a filtered job (just
    sorts it last), and that changing preferences re-filters existing jobs."""
    onboarding = await client.put(
        "/api/profile",
        json={
            "full_name": "Jane Doe",
            "email": "jane@example.com",
            "preferences": {
                "willing_to_relocate": False,
                "preferred_locations": ["Bengaluru"],
            },
        },
    )
    assert onboarding.status_code == 200

    resume = await client.post(
        "/api/resumes",
        data={"label": "SDE Resume", "source_format": "tex"},
        files={"file": ("sde.tex", SDE_RESUME_TEX, "text/x-tex")},
    )
    assert resume.status_code == 201, resume.text
    assert resume.json()["is_primary"] is True

    berlin_job = await client.post(
        "/api/jobs/manual",
        json={
            "company": "Acme",
            "designation": "Backend Engineer",
            "description": JOB_DESCRIPTION,
            "location": "Berlin",
        },
    )
    assert berlin_job.status_code == 201, berlin_job.text
    assert berlin_job.json()["filtered_out_reason"] is not None

    bengaluru_job = await client.post(
        "/api/jobs/manual",
        json={
            "company": "Acme",
            "designation": "Backend Engineer",
            "description": JOB_DESCRIPTION,
            "location": "Bengaluru",
        },
    )
    assert bengaluru_job.status_code == 201, bengaluru_job.text
    assert bengaluru_job.json()["filtered_out_reason"] is None

    ranked = await client.get("/api/jobs/ranked")
    assert ranked.status_code == 200, ranked.text
    ranking = ranked.json()
    assert len(ranking) == 2
    # Never hidden -- both present, kept job first, filtered job last.
    assert ranking[0]["job"]["id"] == bengaluru_job.json()["id"]
    assert ranking[0]["job"]["filtered_out_reason"] is None
    assert ranking[0]["semantic_score"] is not None
    assert ranking[1]["job"]["id"] == berlin_job.json()["id"]
    assert ranking[1]["job"]["filtered_out_reason"] is not None
    assert ranking[1]["semantic_score"] is None

    # Changing preferences re-filters existing jobs, not just future ones.
    relaxed = await client.put(
        "/api/profile",
        json={
            "full_name": "Jane Doe",
            "email": "jane@example.com",
            "preferences": {"willing_to_relocate": True},
        },
    )
    assert relaxed.status_code == 200

    jobs_after = await client.get("/api/jobs")
    by_id = {j["id"]: j for j in jobs_after.json()}
    assert by_id[berlin_job.json()["id"]]["filtered_out_reason"] is None


async def test_ranked_jobs_requires_onboarding_first(client):
    response = await client.get("/api/jobs/ranked")
    assert response.status_code == 412


async def test_notifications_requires_onboarding_first(client):
    response = await client.get("/api/jobs/notifications")
    assert response.status_code == 412


async def test_notifications_qualify_and_clear_once_seen(client):
    """Real semantic scores from score_match's weighted sum are typically
    well below the default notification_threshold for a short test JD/resume
    pair, so this onboards with the threshold pinned to 0.0 (the real,
    user-adjustable Preferences field the Settings page writes to) --
    deterministic, and still exercises the real list_notifications ->
    rank_jobs -> match_resume_to_job path rather than mocking any of it
    away."""
    onboarding = await client.put(
        "/api/profile",
        json={
            "full_name": "Jane Doe",
            "email": "jane@example.com",
            "preferences": {"notification_threshold": 0.0},
        },
    )
    assert onboarding.status_code == 200

    resume = await client.post(
        "/api/resumes",
        data={"label": "SDE Resume", "source_format": "tex"},
        files={"file": ("sde.tex", SDE_RESUME_TEX, "text/x-tex")},
    )
    assert resume.status_code == 201, resume.text

    job = await client.post(
        "/api/jobs/manual",
        json={"company": "Acme", "designation": "Backend Engineer", "description": JOB_DESCRIPTION},
    )
    assert job.status_code == 201, job.text
    job_id = job.json()["id"]

    notifications = await client.get("/api/jobs/notifications")
    assert notifications.status_code == 200, notifications.text
    notified_ids = [n["job"]["id"] for n in notifications.json()]
    assert job_id in notified_ids

    seen = await client.post(f"/api/jobs/{job_id}/notifications/seen")
    assert seen.status_code == 200, seen.text

    after = await client.get("/api/jobs/notifications")
    assert job_id not in [n["job"]["id"] for n in after.json()]

    # Idempotent -- marking an already-seen job seen again is not an error.
    seen_again = await client.post(f"/api/jobs/{job_id}/notifications/seen")
    assert seen_again.status_code == 200


async def test_notification_seen_404s_for_unknown_job(client):
    response = await client.post("/api/jobs/999999/notifications/seen")
    assert response.status_code == 404
