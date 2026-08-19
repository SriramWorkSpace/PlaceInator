"""Job discovery adapters.

Each adapter implements ``JobSource.fetch(query) -> FetchResult``, returning
either postings or ``SourceBlocked(reason)``.

``base.py`` provides the shared infrastructure every adapter must use:
``robots.txt`` checking, per-source token-bucket rate limiting, exponential
backoff, and response caching.

**Hard boundary.** When an adapter meets a login wall, CAPTCHA, or bot-detection
challenge it returns ``SourceBlocked`` and stops. It never solves, evades, or
authenticates through one -- see docs/decisions/0003-job-source-boundary.md.
``SourceBlocked`` is a first-class UI state that offers manual paste, not an
error.

Selector fragility is expected, not exceptional: every adapter ships golden-HTML
fixtures plus a ``live``-marked test, so a break reads as "selectors moved".
"""
