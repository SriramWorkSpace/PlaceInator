"""The MatchResult row doubles as the ranking cache.

`rank_jobs` scores every job on every Dashboard mount, and before this each of
those calls re-embedded every chunk and requirement. These tests pin the
freshness rules and the stored-embedding reuse, with `score_match` stubbed out
so they need no embedding model and stay in the fast default suite.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from sqlalchemy.orm import Session

from placeinator.db.enums import ChunkKind, RequirementKind, SourceKind
from placeinator.db.models import Job, JobRequirement, Profile, Resume, ResumeChunk
from placeinator.matching.scoring import ComponentScore, MatchExplanation
from placeinator.matching.service import (
    _as_naive_utc,
    _is_fresh,
    _stored_vectors,
    match_resume_to_job,
)
from placeinator.matching.vectors import EMBEDDING_DIM, EMBEDDING_MODEL_NAME, encode_vector


def _vector(seed: float) -> bytes:
    return encode_vector(np.full(EMBEDDING_DIM, seed, dtype=np.float32))


@pytest.fixture
def fixtures(session: Session) -> tuple[Resume, Job]:
    profile = Profile(full_name="A", email="a@example.com")
    session.add(profile)
    session.flush()

    resume = Resume(
        profile_id=profile.id,
        label="main",
        source_format="tex",
        source_text="x",
        target_role="Backend Engineer",
    )
    session.add(resume)
    session.flush()
    session.add(
        ResumeChunk(
            resume_id=resume.id,
            kind=ChunkKind.PROJECT_BULLET,
            text="built a thing",
            order_index=0,
            skill_ids=[],
            embedding=_vector(0.1),
            embedding_model=EMBEDDING_MODEL_NAME,
            embedding_dim=EMBEDDING_DIM,
        )
    )

    job = Job(
        source=SourceKind.MANUAL, company="Acme", designation="Backend Engineer", description="d"
    )
    session.add(job)
    session.flush()
    session.add(
        JobRequirement(
            job_id=job.id,
            kind=RequirementKind.RESPONSIBILITY,
            text="build things",
            order_index=0,
            skill_ids=[],
            embedding=_vector(0.2),
            embedding_model=EMBEDDING_MODEL_NAME,
            embedding_dim=EMBEDDING_DIM,
        )
    )
    session.flush()
    return resume, job


@pytest.fixture
def counting_score(monkeypatch) -> list[int]:
    """Replaces score_match with a stub that records how often it ran, so the
    cache is observable without an embedding model."""
    calls = [0]

    def stub(**_kwargs: object) -> MatchExplanation:
        calls[0] += 1
        return MatchExplanation(
            components={"overall": ComponentScore(value=0.5, weight=1.0)}, semantic_score=0.5
        )

    monkeypatch.setattr("placeinator.matching.service.score_match", stub)
    return calls


def test_a_fresh_result_is_reused_instead_of_rescored(session, fixtures, counting_score):
    """The whole point: ranking the same corpus again must not rescore."""
    resume, job = fixtures
    match_resume_to_job(session, resume, job)
    match_resume_to_job(session, resume, job)
    match_resume_to_job(session, resume, job)

    assert counting_score[0] == 1


def test_editing_the_job_invalidates_the_cache(session, fixtures, counting_score):
    resume, job = fixtures
    match_resume_to_job(session, resume, job)

    job.designation = "Staff Backend Engineer"
    session.flush()
    match_resume_to_job(session, resume, job)

    assert counting_score[0] == 2


def test_editing_the_resume_invalidates_the_cache(session, fixtures, counting_score):
    resume, job = fixtures
    match_resume_to_job(session, resume, job)

    resume.target_role = "Platform Engineer"
    session.flush()
    match_resume_to_job(session, resume, job)

    assert counting_score[0] == 2


def test_a_scoring_version_bump_invalidates_the_cache(session, fixtures, counting_score):
    resume, job = fixtures
    result = match_resume_to_job(session, resume, job)

    result.scoring_version = "not-the-current-version"
    session.flush()
    match_resume_to_job(session, resume, job)

    assert counting_score[0] == 2


def test_use_cache_false_forces_a_rescore(session, fixtures, counting_score):
    resume, job = fixtures
    match_resume_to_job(session, resume, job)
    match_resume_to_job(session, resume, job, use_cache=False)

    assert counting_score[0] == 2


def test_a_rescore_that_changes_nothing_still_refreshes_the_row(session, fixtures, counting_score):
    """The stub returns identical scores every time, so no column actually
    changes on the second write. Without an explicit timestamp touch,
    `onupdate` wouldn't fire and the row would look stale forever -- rescoring
    on every single mount, which is the bug this cache exists to prevent."""
    resume, job = fixtures
    match_resume_to_job(session, resume, job)

    job.designation = "Staff Backend Engineer"
    session.flush()
    match_resume_to_job(session, resume, job)
    assert counting_score[0] == 2

    # Nothing has changed since; this must now be a cache hit.
    match_resume_to_job(session, resume, job)
    assert counting_score[0] == 2


def test_freshness_survives_a_tz_aware_timestamp(session, fixtures):
    """A row written in this session holds a tz-aware value while one loaded
    from SQLite is naive. Comparing them directly raises TypeError, and
    match_resume_to_job flushes rather than commits, so both shapes really do
    coexist."""
    resume, job = fixtures
    result = match_resume_to_job(session, resume, job)

    assert result.updated_at.tzinfo is not None, "precondition: the touch leaves it aware"
    assert _is_fresh(result, job, resume) is True


def test_a_result_taken_before_the_job_changed_is_stale(session, fixtures):
    resume, job = fixtures
    result = match_resume_to_job(session, resume, job)
    result.updated_at = datetime.now(UTC) - timedelta(hours=1)

    job.designation = "changed"
    session.flush()

    assert _is_fresh(result, job, resume) is False


# -- stored embeddings ----------------------------------------------------- #


def test_stored_vectors_are_reused_when_the_model_stamp_matches(session, fixtures):
    resume, _ = fixtures
    vectors = _stored_vectors(list(resume.chunks))

    assert vectors is not None
    assert vectors.shape == (1, EMBEDDING_DIM)
    assert vectors[0][0] == pytest.approx(0.1)


def test_a_model_change_falls_back_to_re_embedding(session, fixtures):
    """The provenance stamp exists so a model change is detectable rather than
    silently deserializing into meaningless numbers. None means "re-embed",
    which is always correct."""
    resume, _ = fixtures
    chunk = list(resume.chunks)[0]
    chunk.embedding_model = "some-other-model"

    assert _stored_vectors([chunk]) is None


def test_a_missing_embedding_falls_back_to_re_embedding(session, fixtures):
    resume, _ = fixtures
    chunk = list(resume.chunks)[0]
    chunk.embedding = None

    assert _stored_vectors([chunk]) is None


def test_no_rows_is_an_empty_matrix_not_a_fallback():
    """A resume with no chunks is legitimately empty -- that must not be
    confused with "these embeddings can't be trusted"."""
    vectors = _stored_vectors([])

    assert vectors is not None
    assert vectors.shape == (0, EMBEDDING_DIM)


def test_as_naive_utc_normalizes_both_shapes():
    aware = datetime(2026, 8, 20, 18, 0, tzinfo=UTC)
    naive = datetime(2026, 8, 20, 18, 0)

    assert _as_naive_utc(aware) == naive
    assert _as_naive_utc(naive) == naive
