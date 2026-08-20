"""Job discovery adapters.

Each adapter implements ``JobSource.fetch(query) -> FetchResult``, returning
either postings or ``SourceBlocked(reason)``.

``base.py`` provides the shared infrastructure every adapter must use:
RFC 9309 ``robots.txt`` checking (parsed from raw text, longest-match-wins),
a per-host minimum-interval rate limiter, and one choke point -- ``JobSource.get``
-- that turns both a robots.txt disallow and a transport failure into
``SourceBlocked`` rather than an exception.

Deliberately *not* present, so nobody plans around them: no exponential
backoff, no response caching, no token-bucket burst allowance. At a single
user's request volume none has been needed yet.

**Hard boundary.** When an adapter meets a login wall, CAPTCHA, or bot-detection
challenge it returns ``SourceBlocked`` and stops. It never solves, evades, or
authenticates through one -- see ADR 0003 in docs/decisions.md.
``SourceBlocked`` is a first-class UI state that offers manual paste, not an
error.

Selector fragility is expected, not exceptional: every adapter ships a
``live``-marked test, and the two that actually parse a response (``ats_feed``,
``indeed``) also ship real captured fixtures under tests/fixtures/, so a break
reads as "selectors moved". ``linkedin`` and ``naukri`` have no fixtures
because they have no parser -- both are blocked before any content is
returned, and inventing fixture data for a page never successfully fetched
would be fabricating evidence.
"""
