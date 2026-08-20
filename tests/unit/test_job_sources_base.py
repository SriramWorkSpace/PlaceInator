"""placeinator.jobs.sources.base._can_fetch / _parse_robots_groups --
longest-match-wins robots.txt evaluation (RFC 9309), parsed directly from raw
text rather than through urllib.robotparser's private internals.

This replaced an earlier version built on RobotFileParser.entries /
.default_entry / RuleLine.path / .allowance -- undocumented attributes with
no stability guarantee, which silently changed behavior between Python
3.13.7 (dev machine) and 3.13.15 (CI's windows-latest runner) and made every
one of these tests fail in CI while passing locally. See _parse_robots_groups'
docstring for the full story.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from placeinator.db.enums import SourceKind
from placeinator.jobs.sources.base import (
    FetchResult,
    JobSource,
    SearchQuery,
    SourceBlocked,
    _can_fetch,
    _parse_robots_groups,
)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PlaceInatorBot/0.1"
FIXTURES = Path(__file__).parents[1] / "fixtures" / "indeed"


def test_later_more_specific_disallow_overrides_an_earlier_blanket_allow():
    """The exact shape found on a real host (Indeed) during adapter
    development: User-agent: * opens with "Allow: /", then later disallows a
    specific path. First-match-in-file-order logic would let the early
    Allow: / shadow the Disallow entirely -- this must not."""
    groups = _parse_robots_groups(
        "User-agent: *\nAllow: /\nDisallow: /viewjob\n"
    )
    assert _can_fetch(groups, UA, "https://example.com/jobs?q=engineer") is True
    assert _can_fetch(groups, UA, "https://example.com/viewjob?jk=abc123") is False


def test_blanket_disallow_blocks_everything():
    groups = _parse_robots_groups("User-agent: *\nDisallow: /\n")
    assert _can_fetch(groups, UA, "https://example.com/") is False
    assert _can_fetch(groups, UA, "https://example.com/jobs/search") is False


def test_no_matching_group_defaults_to_allowed():
    groups = _parse_robots_groups("User-agent: SomeOtherBot\nDisallow: /\n")
    assert _can_fetch(groups, UA, "https://example.com/anything") is True


def test_query_string_is_part_of_the_matched_path():
    groups = _parse_robots_groups("User-agent: *\nAllow: /\nDisallow: /search?private=1\n")
    assert _can_fetch(groups, UA, "https://example.com/search?public=1") is True
    assert _can_fetch(groups, UA, "https://example.com/search?private=1") is False


def test_empty_robots_txt_allows_everything():
    assert _can_fetch(_parse_robots_groups(""), UA, "https://example.com/anything") is True


def test_a_more_specific_named_group_is_used_instead_of_the_wildcard_group():
    """A named group matching our UA wins outright over "*" -- its rules are
    used alone, not merged with the wildcard group's."""
    groups = _parse_robots_groups(
        "User-agent: *\nDisallow: /\n\nUser-agent: PlaceInatorBot\nAllow: /\n"
    )
    assert _can_fetch(groups, UA, "https://example.com/anything") is True


def test_real_indeed_robots_txt_matches_live_verified_behavior():
    """Regression test against the real, captured robots.txt (see
    placeinator/jobs/sources/indeed.py's module docstring) -- locks in the
    exact scenario that exposed the original bug: /jobs search is reachable,
    /viewjob is not, for this project's real user agent."""
    text = (FIXTURES / "robots.txt").read_text(encoding="utf-8")
    groups = _parse_robots_groups(text)
    real_ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 PlaceInatorBot/0.1"
    )
    search_url = "https://www.indeed.com/jobs?q=backend+engineer"
    detail_url = "https://www.indeed.com/viewjob?jk=7900206b8b835535"
    assert _can_fetch(groups, real_ua, search_url) is True
    assert _can_fetch(groups, real_ua, detail_url) is False


# -- JobSource.get transport failures ------------------------------------- #


class _PlainSource(JobSource):
    source = SourceKind.INDEED

    def fetch(self, query: SearchQuery) -> FetchResult:  # pragma: no cover - unused
        raise NotImplementedError


@pytest.mark.parametrize(
    "error",
    [
        httpx.ConnectTimeout("timed out"),
        httpx.ReadTimeout("timed out"),
        httpx.ConnectError("name or service not known"),
    ],
)
def test_a_transport_failure_is_source_blocked_not_an_exception(error: httpx.HTTPError):
    """No network, a DNS failure, or a dropped connection is the source being
    unreachable -- ADR 0003 answers that with "offer manual paste", so it must
    not escape fetch() and become a 500 the UI renders as an error."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        raise error

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with _PlainSource(client=client) as source:
        result = source.get("https://example.com/jobs?q=backend")

    assert isinstance(result, SourceBlocked)
    assert "example.com" in result.reason


def test_a_successful_request_still_returns_the_response():
    """The guard above must not swallow the normal path."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        return httpx.Response(200, text="ok")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with _PlainSource(client=client) as source:
        result = source.get("https://example.com/jobs?q=backend")

    assert isinstance(result, httpx.Response)
    assert result.text == "ok"
