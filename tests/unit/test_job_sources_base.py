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

from placeinator.jobs.sources.base import _can_fetch, _parse_robots_groups

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
