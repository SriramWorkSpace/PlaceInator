"""placeinator.career.gaps -- skill-gap aggregation and prioritization
(spec §4). aggregate_skill_gaps is tested directly with hand-built
JobRanking objects, never through rank_jobs itself, mirroring how
JobRanking.overall_score is tested in tests/unit/test_jobs_ranking.py --
the prioritization logic doesn't touch a session, so the test shouldn't
need one either.
"""

from __future__ import annotations

from placeinator.career.gaps import GapEvidence, aggregate_skill_gaps
from placeinator.db.models import Job
from placeinator.jobs.service import JobRanking


def _job(**overrides) -> Job:
    # mapped_column(default=list) only applies at INSERT/flush time, not at
    # bare construction (same gotcha test_jobs_filtering.py's _preferences()
    # helper documents) -- these tests never flush, so required/preferred
    # skill ids must be set explicitly here or they read back as None.
    defaults = dict(
        company="Acme",
        designation="Backend Engineer",
        description="...",
        required_skill_ids=[],
        preferred_skill_ids=[],
    )
    return Job(**{**defaults, **overrides})


def _ranking(**overrides) -> JobRanking:
    defaults = dict(
        job=_job(),
        filtered_out_reason=None,
        semantic_score=None,
        soft_preference_score=0.5,
    )
    return JobRanking(**{**defaults, **overrides})


def test_a_required_skill_the_user_already_has_is_not_a_gap():
    job = _job(required_skill_ids=["python"])
    gaps = aggregate_skill_gaps([_ranking(job=job)], known_skills={"python"})
    assert gaps == []


def test_a_missing_required_skill_becomes_a_gap_with_evidence():
    job = _job(id=1, required_skill_ids=["rust"])
    gaps = aggregate_skill_gaps([_ranking(job=job, soft_preference_score=0.8)], known_skills=set())
    assert len(gaps) == 1
    assert gaps[0].skill_id == "rust"
    assert gaps[0].priority == 0.8  # no semantic score -> overall_score falls back to soft pref
    assert gaps[0].evidence == (
        GapEvidence(job_id=1, company="Acme", designation="Backend Engineer", required=True),
    )


def test_a_skill_appearing_in_multiple_ranked_jobs_accumulates_priority():
    """This is the actual "frequency" half of "frequency x role relevance"
    -- a skill missing from three jobs the user is well-matched to should
    outrank one missing from just one."""
    job_a = _job(id=1, company="A", required_skill_ids=["go"])
    job_b = _job(id=2, company="B", required_skill_ids=["go"])
    job_c = _job(id=3, company="C", required_skill_ids=["rust"])

    gaps = aggregate_skill_gaps(
        [
            _ranking(job=job_a, soft_preference_score=0.5),
            _ranking(job=job_b, soft_preference_score=0.5),
            _ranking(job=job_c, soft_preference_score=0.5),
        ],
        known_skills=set(),
    )

    by_id = {g.skill_id: g for g in gaps}
    assert by_id["go"].priority == 1.0  # 0.5 + 0.5, appeared in two jobs
    assert by_id["rust"].priority == 0.5
    assert len(by_id["go"].evidence) == 2
    # Sorted descending -- "go" (higher priority) comes first.
    assert gaps[0].skill_id == "go"


def test_a_filtered_out_job_never_contributes_a_gap():
    """Hard-filtered jobs (bond terms, salary floor, ...) aren't real
    targets -- their requirements shouldn't drive what to learn next. This
    is enforced by the caller (analyze_skill_gaps filters before calling
    aggregate_skill_gaps), so this test documents that contract by relying
    on JobRanking.overall_score itself: a filtered ranking always scores
    0.0, so even if one slipped through it would contribute nothing --
    belt and suspenders with the caller-side filter."""
    job = _job(required_skill_ids=["rust"])
    ranking = _ranking(job=job, filtered_out_reason="below minimum salary", semantic_score=1.0)
    assert ranking.overall_score == 0.0
    gaps = aggregate_skill_gaps([ranking], known_skills=set())
    assert gaps[0].priority == 0.0


def test_preferred_skills_count_for_less_than_required_ones():
    job = _job(id=1, preferred_skill_ids=["docker"])
    gaps = aggregate_skill_gaps([_ranking(job=job, soft_preference_score=1.0)], known_skills=set())
    assert gaps[0].priority == 0.5  # _PREFERRED_SKILL_WEIGHT
    assert gaps[0].evidence[0].required is False


def test_a_skill_that_is_both_required_and_preferred_only_counts_once_as_required():
    job = _job(id=1, required_skill_ids=["docker"], preferred_skill_ids=["docker"])
    gaps = aggregate_skill_gaps([_ranking(job=job, soft_preference_score=1.0)], known_skills=set())
    assert len(gaps) == 1
    assert gaps[0].priority == 1.0  # not 1.5 -- the preferred pass skips it
    assert len(gaps[0].evidence) == 1
    assert gaps[0].evidence[0].required is True
