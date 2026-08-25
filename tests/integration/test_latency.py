"""Profiles the app against the latency budget in docs/architecture.md.

Four of the five budget rows are measurable here; two are not and stay
manual verification (documented in architecture.md, not silently dropped):
full cold-start-to-interactive needs the real Rust/WebView shell, and idle
memory is an OS-level process metric, neither of which a pytest process can
observe.

Each test prints its measured value (matching the "Measured over 25 jobs:
2.1s cold, 8ms warm" narrative already in architecture.md) and asserts a
LOOSE bound -- several times the target, not the target itself -- so CI
hardware variance doesn't make these flaky while a real regression (10x
slower, not 1.5x) still fails the build.
"""

from __future__ import annotations

import subprocess
import sys
import time
from datetime import UTC, datetime

import numpy as np
import pytest
from sqlalchemy.orm import Session

from placeinator.db.enums import ChunkKind, SourceKind
from placeinator.db.models import Job, MatchResult, Preferences, Profile, Resume, ResumeChunk
from placeinator.jobs.service import rank_jobs
from placeinator.latex.tailoring import tailor_resume
from placeinator.main import HANDSHAKE_PREFIX
from placeinator.matching.chunking import chunk_resume_text
from placeinator.matching.scoring import SCORING_VERSION
from placeinator.matching.vectors import EMBEDDING_DIM, embed_texts, encode_vector

SDE_RESUME_TEX = """
\\documentclass{article}
\\begin{document}

Jane Doe

\\section{Skills}
Python, FastAPI, PostgreSQL, Docker, Kubernetes

\\section{Experience}
\\begin{itemize}
\\item Built a backend service in Python and FastAPI handling 10k requests/sec
\\item Deployed services to Kubernetes and ran CI/CD pipelines
\\end{itemize}

\\section{Projects}
\\begin{itemize}
\\item REST API for a payments platform using FastAPI and PostgreSQL
\\end{itemize}

\\end{document}
"""


def test_sidecar_startup_to_handshake(repo_root):
    """Budget: cold start to interactive, < 1.5 s (whole-app target,
    including the Rust shell + WebView this test can't reach). This times
    only the backend's own contribution -- how much of that 1.5 s budget
    the sidecar itself consumes before it can even be reached -- reusing
    test_handshake.py's exact subprocess-spawn shape."""
    import os

    env = {k: v for k, v in os.environ.items() if not k.startswith("PLACEINATOR_")}
    env["PLACEINATOR_LOG_LEVEL"] = "warning"

    start = time.perf_counter()
    proc = subprocess.Popen(
        [sys.executable, "-m", "placeinator.main"],
        cwd=repo_root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    try:
        deadline = time.monotonic() + 30.0
        line = ""
        while time.monotonic() < deadline:
            line = proc.stdout.readline()  # type: ignore[union-attr]
            if line:
                break
            if proc.poll() is not None:
                raise RuntimeError(f"sidecar exited early (code {proc.returncode})")
        elapsed = time.perf_counter() - start

        assert line.startswith(HANDSHAKE_PREFIX), f"unexpected first stdout line: {line!r}"
        budget_ms = 1500  # whole-app budget; sidecar alone should stay well under it
        print(f"\nsidecar startup -> handshake: {elapsed * 1000:.0f} ms (budget: {budget_ms} ms)")
        # Loose: this is a fresh-Python-process + migration-run cost, not
        # the tight embed/rank numbers below.
        assert elapsed < 5.0, f"sidecar took {elapsed:.2f}s just to hand off -- most of the budget"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.mark.model
def test_embed_one_resume():
    """Budget: embed one resume (~40 chunks), < 200 ms."""
    chunks = chunk_resume_text(SDE_RESUME_TEX)
    texts = [c.text for c in chunks]
    assert texts, "fixture produced no chunks -- test is measuring nothing"

    embed_texts(texts)  # warm the model outside the timed section
    start = time.perf_counter()
    embed_texts(texts)
    elapsed = time.perf_counter() - start

    print(f"\nembed {len(texts)} chunks: {elapsed * 1000:.0f} ms (budget: 200 ms)")
    assert elapsed < 1.0, f"embedding {len(texts)} chunks took {elapsed:.2f}s -- 5x the budget"


@pytest.mark.model
def test_rank_500_cached_jobs(session: Session):
    """Budget: rank 500 cached jobs, < 50 ms. Every job gets an already-fresh
    MatchResult, so this measures the cache-hit path the budget line
    actually describes ("Precomputed vectors, one NumPy matmul"), not a cold
    rescore."""
    profile = Profile(full_name="Jane Doe", email="jane@example.com")
    profile.preferences = Preferences()
    session.add(profile)
    session.flush()

    resume = Resume(
        profile_id=profile.id,
        label="SDE",
        source_format="tex",
        source_text=SDE_RESUME_TEX,
        is_primary=True,
    )
    session.add(resume)
    session.flush()
    session.add(
        ResumeChunk(
            resume_id=resume.id,
            kind=ChunkKind.SKILL,
            text="Python",
            order_index=0,
            skill_ids=["python"],
            embedding=encode_vector(
                np.ones(EMBEDDING_DIM, dtype=np.float32) / np.sqrt(EMBEDDING_DIM)
            ),
            embedding_model="test",
            embedding_dim=EMBEDDING_DIM,
        )
    )
    session.flush()

    jobs = []
    for i in range(500):
        job = Job(
            source=SourceKind.MANUAL,
            company=f"Company {i}",
            designation="Backend Engineer",
            description="...",
            required_skill_ids=[],
            preferred_skill_ids=[],
        )
        session.add(job)
        session.flush()
        jobs.append(job)

    # Captured only *after* every Job row above is already committed, not
    # before the loop. Job.updated_at comes from TimestampMixin's
    # server_default=func.now() (placeinator/db/base.py), which on SQLite is
    # CURRENT_TIMESTAMP -- whole-SECOND granularity, unlike this Python
    # microsecond timestamp. Capturing `now` before a ~250ms+ setup loop left
    # a real race: if the loop straddled a wall-clock second boundary, jobs
    # committed after the tick got a server-computed updated_at *later* than
    # the precomputed `now`, failing _is_fresh's freshness check during the
    # timed rank_jobs() call below and forcing a full cold rescore instead of
    # the cache-hit path this test exists to measure. Confirmed directly by
    # instrumented reproduction: 0-458 of 500 jobs went spuriously stale per
    # run depending on where in the second `now` landed, correlating exactly
    # with elapsed time from ~100ms up to ~35s. Capturing `now` after every
    # Job is already persisted makes it >= every Job.updated_at by
    # construction (same wall clock, strictly later instant), eliminating
    # the race rather than tolerating it.
    now = datetime.now(UTC)
    for job in jobs:
        session.add(
            MatchResult(
                job_id=job.id,
                resume_id=resume.id,
                semantic_score=0.5,
                personalized_score=0.5,
                explanation={},
                scoring_version=SCORING_VERSION,
                updated_at=now,
            )
        )
    session.flush()
    # Freshness also requires the row's updated_at >= job/resume updated_at
    # (see placeinator.matching.service._is_fresh); resume was flushed before
    # the job loop and every job is now guaranteed strictly before `now` by
    # construction (see above), so this holds deterministically. Verified,
    # not assumed: every job must be at or before `now`, or the cache-hit
    # path below wouldn't actually be exercised and the measurement would be
    # meaningless.
    now_naive = now.astimezone(UTC).replace(tzinfo=None)
    stale = [j.id for j in jobs if j.updated_at > now_naive]
    assert not stale, (
        f"{len(stale)} job(s) have updated_at after the reference timestamp -- "
        "the freshness check would force a cold rescore, not the cache-hit path "
        "this test measures"
    )

    start = time.perf_counter()
    rankings = rank_jobs(session, profile)
    elapsed = time.perf_counter() - start

    assert len(rankings) == 500
    print(f"\nrank {len(rankings)} cached jobs: {elapsed * 1000:.0f} ms (budget: 50 ms)")
    assert elapsed < 0.5, f"ranking 500 cached jobs took {elapsed * 1000:.0f}ms -- 10x the budget"


@pytest.mark.model
def test_tailor_a_resume(session: Session):
    """Budget: tailor a resume, < 2 s."""
    profile = Profile(full_name="Jane Doe", email="jane@example.com")
    session.add(profile)
    session.flush()

    resume = Resume(
        profile_id=profile.id, label="SDE", source_format="tex", source_text=SDE_RESUME_TEX
    )
    session.add(resume)
    session.flush()
    for chunk in chunk_resume_text(SDE_RESUME_TEX):
        session.add(
            ResumeChunk(
                resume_id=resume.id,
                kind=chunk.kind,
                section=chunk.section,
                text=chunk.text,
                order_index=0,
                span_start=chunk.span_start,
                span_end=chunk.span_end,
                skill_ids=sorted(chunk.skill_ids),
            )
        )
    session.flush()

    job = Job(
        source=SourceKind.MANUAL,
        company="Acme",
        designation="Backend Engineer",
        description="Python, FastAPI, Kubernetes",
        required_skill_ids=["python", "fastapi"],
        preferred_skill_ids=[],
    )
    session.add(job)
    session.flush()

    tailor_resume(session, resume, job)  # warm up (chunking/embedding paths)
    start = time.perf_counter()
    tailor_resume(session, resume, job)
    elapsed = time.perf_counter() - start

    print(f"\ntailor a resume: {elapsed * 1000:.0f} ms (budget: 2000 ms)")
    assert elapsed < 10.0, f"tailoring took {elapsed:.2f}s -- 5x the budget"
