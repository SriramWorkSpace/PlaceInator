"""Unit tests for the Naukri adapter, against the real 403 Akamai
Access-Denied shape verified live -- see
placeinator/jobs/sources/naukri.py's module docstring for how this was
confirmed. No network access; httpx.MockTransport serves the fixtures."""

from __future__ import annotations

import httpx

from placeinator.jobs.sources.base import SearchQuery, SourceBlocked
from placeinator.jobs.sources.naukri import NaukriSource

_AKAMAI_ACCESS_DENIED = (
    "<HTML><HEAD><TITLE>Access Denied</TITLE></HEAD><BODY><H1>Access Denied</H1>"
    "You don't have permission to access this server."
    "</BODY></HTML>"
)


def test_edge_bot_block_is_reported_as_source_blocked():
    """Naukri's robots.txt itself 403s, which base.py's fetch-failure
    handling treats as "presume allowed" (the general, correct default) --
    so the real request going through and getting a 403 back is what this
    adapter must actually catch."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(403, text=_AKAMAI_ACCESS_DENIED)
        return httpx.Response(403, text=_AKAMAI_ACCESS_DENIED)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with NaukriSource(client=client) as source:
        result = source.fetch(SearchQuery(keywords="backend engineer"))

    assert isinstance(result, SourceBlocked)
    assert "403" in result.reason


def test_never_raises_if_naukri_ever_starts_serving_200():
    """No parser has been verified against a real response -- a surprise 200
    must degrade to SourceBlocked, not fabricate postings from an unparsed
    page."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(403, text=_AKAMAI_ACCESS_DENIED)
        return httpx.Response(200, text="<html>a real job search page</html>")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with NaukriSource(client=client) as source:
        result = source.fetch(SearchQuery(keywords="backend engineer"))

    assert isinstance(result, SourceBlocked)


def test_keyword_slug_is_url_safe():
    seen_paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(403, text=_AKAMAI_ACCESS_DENIED)
        seen_paths.append(request.url.path)
        return httpx.Response(403, text=_AKAMAI_ACCESS_DENIED)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with NaukriSource(client=client) as source:
        source.fetch(SearchQuery(keywords="Backend Engineer"))

    assert seen_paths == ["/backend-engineer-jobs"]
