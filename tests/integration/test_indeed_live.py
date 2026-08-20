"""Hits the real indeed.com search page. Opt-in (-m live), since the default
suite must stay offline-safe and this depends on Indeed's page structure and
bot-detection posture staying stable -- exactly the fragility ADR 0003
expects from anything touching a live third party."""

from __future__ import annotations

import pytest

from placeinator.jobs.sources.base import SearchQuery, SourceBlocked
from placeinator.jobs.sources.indeed import IndeedSource

pytestmark = pytest.mark.live


def test_indeed_live_search_returns_postings():
    with IndeedSource() as source:
        result = source.fetch(SearchQuery(keywords="backend engineer", location="Remote"))

    # Not asserting success unconditionally: Indeed's bot posture can change,
    # and per ADR 0003 a real SourceBlocked here is a legitimate outcome, not
    # a test failure. What must hold either way is "never raises, never
    # returns garbage".
    if isinstance(result, SourceBlocked):
        assert result.reason
        return

    assert len(result) > 0
    first = result[0]
    assert first.company
    assert first.designation
    assert first.source_ref.startswith("indeed:")
