"""placeinator.jobs.service.JobRanking.overall_score and the notification
qualification threshold -- pure logic, no DB needed since JobRanking never
touches the job/session itself beyond holding a reference.
"""

from __future__ import annotations

from placeinator.db.models import Job
from placeinator.jobs.service import (
    NOTIFICATION_THRESHOLD,
    JobRanking,
    _qualifies_for_notification,
)


def _ranking(**overrides) -> JobRanking:
    defaults = dict(
        job=Job(company="Acme", designation="Backend Engineer", description="..."),
        filtered_out_reason=None,
        semantic_score=None,
        soft_preference_score=0.5,
    )
    return JobRanking(**{**defaults, **overrides})


def test_filtered_job_scores_zero_regardless_of_other_signals():
    ranking = _ranking(filtered_out_reason="outside preferred locations", semantic_score=0.9)
    assert ranking.overall_score == 0.0


def test_no_primary_resume_falls_back_to_soft_preference_alone():
    ranking = _ranking(semantic_score=None, soft_preference_score=0.8)
    assert ranking.overall_score == 0.8


def test_overall_score_combines_semantic_and_soft_preference():
    ranking = _ranking(semantic_score=1.0, soft_preference_score=0.0)
    # Weighted toward semantic match; some soft-preference influence remains.
    assert 0.0 < ranking.overall_score < 1.0


def test_filtered_job_never_qualifies_for_notification():
    ranking = _ranking(filtered_out_reason="below minimum salary", semantic_score=1.0)
    assert not _qualifies_for_notification(ranking)


def test_no_semantic_score_never_qualifies_for_notification():
    """No primary resume means no semantic score -- there is nothing to say
    "this matches you" about, so it can't be a personalized notification."""
    ranking = _ranking(semantic_score=None, soft_preference_score=1.0)
    assert not _qualifies_for_notification(ranking)


def test_score_below_threshold_does_not_qualify():
    ranking = _ranking(semantic_score=NOTIFICATION_THRESHOLD - 0.3, soft_preference_score=0.0)
    assert ranking.overall_score < NOTIFICATION_THRESHOLD
    assert not _qualifies_for_notification(ranking)


def test_score_at_or_above_threshold_qualifies():
    ranking = _ranking(semantic_score=1.0, soft_preference_score=1.0)
    assert ranking.overall_score >= NOTIFICATION_THRESHOLD
    assert _qualifies_for_notification(ranking)
