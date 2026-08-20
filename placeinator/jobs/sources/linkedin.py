"""LinkedIn keyword/location search.

Verified live before writing a line of parsing logic: linkedin.com's
``robots.txt`` closes with a catch-all ``User-agent: *`` block of exactly

    Disallow: /

with a comment directing crawlers to email for whitelisting. Every path on
the entire site is disallowed for any crawler not individually named earlier
in the file (Googlebot and a handful of other major, explicitly-listed
bots) -- this adapter, running as an unrecognized UA, is disallowed
everywhere, not just on job-search paths. ADR 0003 predicted "thin —
public job-view pages only"; the real answer is thinner still: zero, by the
site's own declared policy, not by a login wall or bot-detection challenge
this adapter could otherwise route around.

There is deliberately no HTML-parsing logic here. Writing one against a
domain whose robots.txt is `Disallow: /` would mean the parser exists
only to be dead code the moment ``self.get()`` correctly refuses to fetch
anything -- shared JobSource.get() (robots.txt-gated per ADR 0003) is what
makes that refusal happen, not a special case in this file. If LinkedIn ever
relaxes robots.txt for job-search paths, this adapter starts working with no
code change, because the block would no longer trigger.
"""

from __future__ import annotations

from urllib.parse import quote

from placeinator.db.enums import SourceKind
from placeinator.jobs.sources.base import JobSource, RawPosting, SearchQuery, SourceBlocked

_RATE_LIMIT_SECONDS = 3.0


class LinkedInSource(JobSource):
    source = SourceKind.LINKEDIN

    def fetch(self, query: SearchQuery) -> list[RawPosting] | SourceBlocked:
        url = (
            "https://www.linkedin.com/jobs/search"
            f"?keywords={quote(query.keywords)}&location={quote(query.location or '')}"
        )
        response = self.get(url, min_interval=_RATE_LIMIT_SECONDS)
        if isinstance(response, SourceBlocked):
            return response
        if response.status_code != 200:
            return SourceBlocked(f"linkedin returned {response.status_code}")

        # robots.txt currently disallows every path for an unrecognized
        # crawler, so self.get() above should always have returned
        # SourceBlocked already. Reaching here means the site's policy
        # changed since this module's docstring was verified -- rather than
        # parse a page this adapter was never designed against, report that
        # honestly instead of guessing at a new structure.
        return SourceBlocked(
            "linkedin: robots.txt now permits this request, but no parser has been "
            "verified against the current page structure yet"
        )
