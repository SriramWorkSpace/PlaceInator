"""Unit tests for the ats_feed adapter, against real captured API responses
(tests/fixtures/ats_feed/) rather than fabricated ones -- see
placeinator/jobs/sources/ats_feed.py's module docstring for how they were
captured. No network access; httpx.MockTransport serves the fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from placeinator.db.enums import WorkMode
from placeinator.jobs.sources.ats_feed import AtsFeedSource
from placeinator.jobs.sources.base import SearchQuery, SourceBlocked

FIXTURES = Path(__file__).parents[1] / "fixtures" / "ats_feed"


def _load(name: str) -> dict | list:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _mock_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    host = request.url.host

    if path == "/robots.txt":
        # Matches the real, live-verified behaviour: Greenhouse and Lever
        # serve one, Ashby doesn't -- both cases are exercised by routing
        # every mocked host through the "no robots.txt -> allow" path,
        # which is the one this adapter actually depends on working.
        return httpx.Response(404)

    if host == "boards-api.greenhouse.io":
        if path == "/v1/boards/acme/jobs":
            return httpx.Response(200, json=_load("greenhouse_list.json"))
        if path == "/v1/boards/acme/jobs/8077887":
            return httpx.Response(200, json=_load("greenhouse_detail_8077887.json"))
        if path == "/v1/boards/acme/jobs/8023928":
            # Only one detail fixture was captured; the adapter must
            # degrade to an empty description, not crash, on the other.
            return httpx.Response(404)
        if path == "/v1/boards/blocked-co/jobs":
            return httpx.Response(403)

    if host == "api.lever.co" and path == "/v0/postings/acme":
        return httpx.Response(200, json=_load("lever_postings.json"))

    if host == "api.ashbyhq.com" and path == "/posting-api/job-board/acme":
        return httpx.Response(200, json=_load("ashby_board.json"))

    raise AssertionError(f"unexpected request: {request.method} {request.url}")


@pytest.fixture
def source() -> AtsFeedSource:
    client = httpx.Client(transport=httpx.MockTransport(_mock_handler))
    with AtsFeedSource(client=client) as src:
        yield src


def test_greenhouse_postings_are_normalized(source: AtsFeedSource):
    result = source.fetch(SearchQuery(companies=("greenhouse:acme",)))

    assert not isinstance(result, SourceBlocked)
    assert len(result) == 2

    first = result[0]
    assert first.source_ref == "greenhouse:acme:8077887"
    assert first.company == "Stripe"  # from the fixture's company_name field
    assert first.designation.strip() == "Account Executive, Bridge"
    assert first.url and first.url.startswith("https://stripe.com/")
    assert first.location == "SF, NYC, SEA, CHI"
    # The detail fixture's real HTML content, double-unescaped and stripped.
    assert "Stripe is a financial infrastructure platform" in first.description
    assert "<" not in first.description


def test_greenhouse_missing_detail_degrades_to_empty_description(source: AtsFeedSource):
    result = source.fetch(SearchQuery(companies=("greenhouse:acme",)))
    assert not isinstance(result, SourceBlocked)
    second = result[1]
    assert second.source_ref == "greenhouse:acme:8023928"
    assert second.description == ""


def test_greenhouse_blocked_source_returns_source_blocked_not_raise(source: AtsFeedSource):
    result = source.fetch(SearchQuery(companies=("greenhouse:blocked-co",)))
    assert isinstance(result, SourceBlocked)
    assert "403" in result.reason


def test_lever_postings_are_normalized(source: AtsFeedSource):
    result = source.fetch(SearchQuery(companies=("lever:acme",)))

    assert not isinstance(result, SourceBlocked)
    assert len(result) == 2
    first = result[0]
    assert first.source_ref.startswith("lever:acme:")
    assert first.designation == "AbelsonTaylor Writer"
    assert first.location == "Arlington, TX"
    # descriptionPlain is used directly, not re-derived from HTML.
    assert "Welcome to the Demo Job Listing" in first.description or first.description


def test_ashby_postings_are_normalized(source: AtsFeedSource):
    result = source.fetch(SearchQuery(companies=("ashby:acme",)))

    assert not isinstance(result, SourceBlocked)
    assert len(result) == 2
    first = result[0]
    assert first.source_ref.startswith("ashby:acme:")
    assert first.designation == "Senior / Staff Fullstack Engineer"
    assert first.work_mode == WorkMode.REMOTE  # fixture's isRemote: true
    assert "<" not in first.description
    assert "Linear" in first.description


def test_fetch_across_multiple_platforms_in_one_query(source: AtsFeedSource):
    result = source.fetch(
        SearchQuery(companies=("greenhouse:acme", "lever:acme", "ashby:acme"))
    )
    assert not isinstance(result, SourceBlocked)
    assert len(result) == 6  # 2 postings from each of the three platforms


def test_empty_companies_returns_empty_list_without_any_request():
    def fail_on_any_request(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"no request should be made, got: {request.url}")

    client = httpx.Client(transport=httpx.MockTransport(fail_on_any_request))
    with AtsFeedSource(client=client) as source:
        result = source.fetch(SearchQuery())
    assert result == []


def test_malformed_company_entry_raises_a_clear_error(source: AtsFeedSource):
    with pytest.raises(ValueError, match="platform:company-slug"):
        source.fetch(SearchQuery(companies=("not-a-valid-entry",)))
