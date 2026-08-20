"""Hits the real linkedin.com robots.txt. Opt-in (-m live) -- confirms the
site's declared crawler policy hasn't changed since
placeinator/jobs/sources/linkedin.py's docstring was written, not a
functional test of job data (there is none reachable to test)."""

from __future__ import annotations

import pytest

from placeinator.jobs.sources.base import SearchQuery, SourceBlocked
from placeinator.jobs.sources.linkedin import LinkedInSource

pytestmark = pytest.mark.live


def test_linkedin_live_search_is_blocked():
    """Documents the current real state rather than assuming it: if this
    ever fails because LinkedIn actually served content, that is a
    meaningful signal the adapter's docstring and design need revisiting,
    not a bug to silently work around."""
    with LinkedInSource() as source:
        result = source.fetch(SearchQuery(keywords="backend engineer", location="Remote"))
    assert isinstance(result, SourceBlocked)
    assert result.reason
