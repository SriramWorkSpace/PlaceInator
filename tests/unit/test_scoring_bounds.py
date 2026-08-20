"""Component scores are contractually in [0, 1] -- MatchResult.explanation is
user-facing and the weighted sum in score_match assumes the bound holds.

These are pure-arithmetic tests with no embedding model, so they run in the
fast default suite. The model-marked tests in tests/integration/test_scoring.py
assert the same property on real vectors; this file pins the arithmetic that
made those fail on CI while passing locally.
"""

from __future__ import annotations

import pytest

from placeinator.matching.scoring import _clamp_unit


def test_the_exact_value_that_broke_ci_is_clamped():
    """Cosine similarity of two near-identical float32 vectors can land a few
    ULPs above 1.0. This is the literal value CI produced for an exact
    role-title match ("Backend Engineer" against itself) on a runner whose
    vector instructions differ from the dev machine's, where the same code
    stayed just under 1.0."""
    assert _clamp_unit(1.0000001192092896) == 1.0


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (-0.0000001, 0.0),
        (-0.5, 0.0),
        (0.0, 0.0),
        (0.5, 0.5),
        (1.0, 1.0),
        (1.5, 1.0),
    ],
)
def test_values_are_bounded_at_both_ends(value: float, expected: float):
    """Both ends, not just the lower one -- clamping only the floor is what
    let the overflow through."""
    assert _clamp_unit(value) == expected


def test_a_value_already_in_range_is_returned_unchanged():
    """The clamp must not perturb ordinary scores; ranking depends on the
    exact values, not just their bounds."""
    for value in (0.123456789, 0.42, 0.9999999):
        assert _clamp_unit(value) == value
