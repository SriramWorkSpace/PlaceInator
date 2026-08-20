"""placeinator.jobs.sources.base._can_fetch -- longest-match-wins robots.txt
evaluation, replacing RobotFileParser.can_fetch's first-match-in-file-order
behavior (see the docstring on _can_fetch for how that was discovered).
"""

from __future__ import annotations

from urllib.robotparser import RobotFileParser

from placeinator.jobs.sources.base import _can_fetch

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PlaceInatorBot/0.1"


def _parser(lines: list[str]) -> RobotFileParser:
    parser = RobotFileParser()
    parser.parse(lines)
    return parser


def test_later_more_specific_disallow_overrides_an_earlier_blanket_allow():
    """The exact shape found on a real host (Indeed) during adapter
    development: User-agent: * opens with "Allow: /", then later disallows a
    specific path. stdlib's can_fetch would let the early Allow: / shadow
    the Disallow entirely -- this must not."""
    parser = _parser(
        [
            "User-agent: *",
            "Allow: /",
            "Disallow: /viewjob",
        ]
    )
    assert _can_fetch(parser, UA, "https://example.com/jobs?q=engineer") is True
    assert _can_fetch(parser, UA, "https://example.com/viewjob?jk=abc123") is False


def test_blanket_disallow_blocks_everything():
    parser = _parser(["User-agent: *", "Disallow: /"])
    assert _can_fetch(parser, UA, "https://example.com/") is False
    assert _can_fetch(parser, UA, "https://example.com/jobs/search") is False


def test_no_matching_entry_defaults_to_allowed():
    parser = _parser(["User-agent: SomeOtherBot", "Disallow: /"])
    assert _can_fetch(parser, UA, "https://example.com/anything") is True


def test_query_string_is_part_of_the_matched_path():
    parser = _parser(["User-agent: *", "Allow: /", "Disallow: /search?private=1"])
    assert _can_fetch(parser, UA, "https://example.com/search?public=1") is True
    assert _can_fetch(parser, UA, "https://example.com/search?private=1") is False


def test_allow_all_short_circuits():
    parser = RobotFileParser()
    parser.allow_all = True  # type: ignore[attr-defined]
    assert _can_fetch(parser, UA, "https://example.com/anything") is True
