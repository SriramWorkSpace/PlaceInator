"""Unit tests for the LinkedIn adapter, against LinkedIn's real robots.txt
shape (a catch-all "Disallow: /" for any unrecognized crawler) -- see
placeinator/jobs/sources/linkedin.py's module docstring for how this was
verified. No network access; httpx.MockTransport serves the fixtures."""

from __future__ import annotations

import httpx
import pytest

from placeinator.jobs.sources.base import SearchQuery, SourceBlocked
from placeinator.jobs.sources.linkedin import LinkedInSource

# The real robots.txt's catch-all block, verified live -- see the module
# docstring. Trimmed to just the part that determines this adapter's
# behavior, not the dozens of named-bot-specific blocks above it.
_ROBOTS_TXT = "User-agent: *\nDisallow: /\n"


def test_every_request_is_blocked_by_robots_txt():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=_ROBOTS_TXT)
        raise AssertionError("must never reach a real search request -- robots.txt disallows all")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with LinkedInSource(client=client) as source:
        result = source.fetch(SearchQuery(keywords="backend engineer", location="Remote"))

    assert isinstance(result, SourceBlocked)
    assert "robots.txt" in result.reason


def test_never_raises_if_robots_txt_ever_relaxes():
    """If the site's policy ever changes, this must still degrade to
    SourceBlocked (no verified parser exists), not crash or fabricate
    postings from an unparsed response."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        return httpx.Response(200, text="<html>a real job search page</html>")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with LinkedInSource(client=client) as source:
        result = source.fetch(SearchQuery(keywords="backend engineer"))

    assert isinstance(result, SourceBlocked)


@pytest.mark.parametrize("status", [403, 500])
def test_non_200_non_blocked_response_returns_source_blocked(status: int):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        return httpx.Response(status)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with LinkedInSource(client=client) as source:
        result = source.fetch(SearchQuery(keywords="backend engineer"))

    assert isinstance(result, SourceBlocked)
