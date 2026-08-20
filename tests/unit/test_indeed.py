"""Unit tests for the Indeed adapter, against a real captured (and trimmed)
search-results page and the real robots.txt -- see
placeinator/jobs/sources/indeed.py's module docstring for how the fixture
was captured. No network access; httpx.MockTransport serves the fixtures."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from placeinator.db.enums import JobType, WorkMode
from placeinator.jobs.sources.base import SearchQuery, SourceBlocked
from placeinator.jobs.sources.indeed import IndeedSource

FIXTURES = Path(__file__).parents[1] / "fixtures" / "indeed"


def _mock_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/robots.txt":
        return httpx.Response(200, text=(FIXTURES / "robots.txt").read_text(encoding="utf-8"))
    if request.url.path == "/jobs":
        return httpx.Response(
            200, text=(FIXTURES / "search_results.html").read_text(encoding="utf-8")
        )
    raise AssertionError(f"unexpected request: {request.method} {request.url}")


@pytest.fixture
def source() -> IndeedSource:
    client = httpx.Client(transport=httpx.MockTransport(_mock_handler))
    with IndeedSource(client=client) as src:
        yield src


def test_search_results_are_normalized(source: IndeedSource):
    result = source.fetch(SearchQuery(keywords="backend engineer", location="Remote"))

    assert not isinstance(result, SourceBlocked)
    assert len(result) == 3

    first = result[0]
    assert first.source_ref == "indeed:7900206b8b835535"
    assert first.company == "GoGoGrandparent"
    assert first.designation == "Backend Engineer"
    assert first.location == "Wilmington, DE 19802"
    assert first.work_mode == WorkMode.REMOTE
    assert first.url == "https://www.indeed.com/viewjob?jk=7900206b8b835535"
    # snippet HTML stripped to plain text, matching the real captured content.
    # html_to_text separates every node (including inline <b> tags) with a
    # newline, so "Mentor other" and "engineers" land on adjacent lines
    # rather than as one contiguous phrase.
    assert "<" not in first.description
    assert "Mentor other" in first.description
    assert "engineers" in first.description


def test_second_organic_result_is_normalized(source: IndeedSource):
    result = source.fetch(SearchQuery(keywords="backend engineer", location="Remote"))
    assert not isinstance(result, SourceBlocked)
    second = result[1]
    assert second.company == "Zap Solutions Europe"
    assert second.designation == "Software Engineer, Backend"
    assert second.source_ref == "indeed:8b1a1206782535fb"


def test_ambiguous_job_types_resolve_to_unknown_not_a_guess(source: IndeedSource):
    """The sponsored fixture entry genuinely lists three simultaneous
    job-type labels (Contract/Full-time/Part-time) -- reporting any one of
    them would be inventing a fact the source itself doesn't assert."""
    result = source.fetch(SearchQuery(keywords="backend engineer", location="Remote"))
    assert not isinstance(result, SourceBlocked)
    sponsored = result[2]
    assert sponsored.company == "DataAnnotation"
    assert sponsored.job_type == JobType.UNKNOWN


def test_never_fetches_viewjob_even_though_the_url_is_constructed():
    """robots.txt disallows /viewjob for a generic crawler -- the adapter
    must never request it, only build the URL for the user to click through
    themselves. A handler that raises on that path is the enforcement."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=(FIXTURES / "robots.txt").read_text(encoding="utf-8"))
        if request.url.path == "/jobs":
            return httpx.Response(
                200, text=(FIXTURES / "search_results.html").read_text(encoding="utf-8")
            )
        if request.url.path == "/viewjob":
            raise AssertionError("adapter must never fetch /viewjob -- robots.txt disallows it")
        raise AssertionError(f"unexpected request: {request.url}")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with IndeedSource(client=client) as source:
        result = source.fetch(SearchQuery(keywords="backend engineer"))
    assert not isinstance(result, SourceBlocked)


def test_non_200_response_returns_source_blocked():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(503)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with IndeedSource(client=client) as source:
        result = source.fetch(SearchQuery(keywords="backend engineer"))
    assert isinstance(result, SourceBlocked)
    assert "503" in result.reason


def test_missing_data_blob_returns_source_blocked_not_a_crash():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, text="<html><body>no jobs here</body></html>")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with IndeedSource(client=client) as source:
        result = source.fetch(SearchQuery(keywords="backend engineer"))
    assert isinstance(result, SourceBlocked)


def test_robots_txt_disallow_blocks_before_any_search_request():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /\n")
        raise AssertionError("search request must not happen when robots.txt disallows it")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with IndeedSource(client=client) as source:
        result = source.fetch(SearchQuery(keywords="backend engineer"))
    assert isinstance(result, SourceBlocked)
