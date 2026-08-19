"""Hits the real Greenhouse/Lever/Ashby APIs. Opt-in (-m live), since the
default suite must stay offline-safe and these depend on real companies'
boards staying open -- exactly the fragility ADR 0003 expects from anything
touching a live third party."""

from __future__ import annotations

import pytest

from placeinator.jobs.sources.ats_feed import AtsFeedSource
from placeinator.jobs.sources.base import SearchQuery, SourceBlocked

pytestmark = pytest.mark.live


def test_greenhouse_live_fetch_returns_postings():
    with AtsFeedSource() as source:
        result = source.fetch(SearchQuery(companies=("greenhouse:stripe",)))
    assert not isinstance(result, SourceBlocked)
    assert len(result) > 0
    assert result[0].designation


def test_ashby_live_fetch_returns_postings():
    with AtsFeedSource() as source:
        result = source.fetch(SearchQuery(companies=("ashby:linear",)))
    assert not isinstance(result, SourceBlocked)
    assert len(result) > 0
    assert result[0].designation


def test_lever_live_fetch_returns_postings():
    # leverdemo is Lever's own public example board (383 postings when this
    # was written) -- used instead of a real company's board specifically
    # because it's meant to stay populated and stable for exactly this.
    with AtsFeedSource() as source:
        result = source.fetch(SearchQuery(companies=("lever:leverdemo",)))
    assert not isinstance(result, SourceBlocked)
    assert len(result) > 0
    assert result[0].designation
