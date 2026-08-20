"""Hits the real naukri.com. Opt-in (-m live) -- confirms the site's edge
bot-detection posture hasn't changed since
placeinator/jobs/sources/naukri.py's docstring was written, not a functional
test of job data (none was reachable to test against)."""

from __future__ import annotations

import pytest

from placeinator.jobs.sources.base import SearchQuery, SourceBlocked
from placeinator.jobs.sources.naukri import NaukriSource

pytestmark = pytest.mark.live


def test_naukri_live_search_is_blocked():
    """Documents the current real state rather than assuming it: if this
    ever fails because Naukri actually served content, that is a meaningful
    signal worth investigating -- it would mean a real parser can finally be
    written -- not a bug to silently work around."""
    with NaukriSource() as source:
        result = source.fetch(SearchQuery(keywords="backend engineer"))
    assert isinstance(result, SourceBlocked)
    assert result.reason
