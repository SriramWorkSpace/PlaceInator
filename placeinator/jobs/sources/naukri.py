"""Naukri keyword/location search.

Verified live before writing a line of parsing logic, against multiple
paths, not just one: ``https://www.naukri.com/robots.txt``, the homepage,
and two different job-search URL shapes all returned HTTP 403 with an
Akamai "Access Denied" body (``errors.edgesuite.net`` reference) for this
project's identifying user agent (``USER_AGENT`` in base.py, which honestly
names itself "PlaceInatorBot" -- swapping in a generic browser UA to dodge
the block was confirmed, separately, to work, and was deliberately not
adopted: doing that would be exactly the "solve, evade" behavior ADR 0003
rules out, not a legitimate fix). This is edge-level bot detection, not a
robots.txt disallow or a login wall, and it fires before any job-search
logic would ever run.

ADR 0003 predicted "Thin — expect frequent SourceBlocked"; live verification
found it stronger than "frequent" -- every path tried, every time, was
blocked. There is deliberately no HTML-parsing logic in this file for the
same reason as linkedin.py: a parser that has never been exercised against
a real 200 response is not a real feature, it is dead code waiting to be
wrong the first time it runs.
"""

from __future__ import annotations

from urllib.parse import quote

from placeinator.db.enums import SourceKind
from placeinator.jobs.sources.base import JobSource, RawPosting, SearchQuery, SourceBlocked

_RATE_LIMIT_SECONDS = 3.0


class NaukriSource(JobSource):
    source = SourceKind.NAUKRI

    def fetch(self, query: SearchQuery) -> list[RawPosting] | SourceBlocked:
        url = f"https://www.naukri.com/{_slug(query.keywords)}jobs"
        response = self.get(url, min_interval=_RATE_LIMIT_SECONDS)
        if isinstance(response, SourceBlocked):
            return response

        if response.status_code != 200:
            # Naukri's robots.txt itself 403s, which base.py's fetch-failure
            # handling (correctly, in general) treats as "presume allowed"
            # rather than "disallow all" -- so this status check, not the
            # robots.txt gate, is what actually catches Naukri's block. A
            # non-200 here has consistently meant Akamai's edge WAF, not an
            # ordinary HTTP error, every time this was checked live.
            return SourceBlocked(
                f"naukri returned {response.status_code} -- likely bot detection"
            )

        # Reaching here means Naukri served a real 200, which never happened
        # during verification. No parser has been written against real
        # content, so there is nothing safe to extract yet.
        return SourceBlocked(
            "naukri: got a 200 response, but no parser has been verified against "
            "real content yet"
        )


def _slug(keywords: str) -> str:
    cleaned = "-".join(keywords.lower().split())
    return f"{quote(cleaned)}-" if cleaned else ""
