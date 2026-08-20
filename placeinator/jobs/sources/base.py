"""Shared infrastructure every job-source adapter must use.

Enforces the boundary ADR 0003 sets: ``robots.txt`` is checked before every
fetch, requests are rate-limited per host, and a blocked source returns
``SourceBlocked`` rather than raising -- the UI treats that as "offer manual
paste", not an error.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from urllib.parse import quote, unquote, urlparse, urlunparse
from urllib.robotparser import RobotFileParser

import httpx
from selectolax.parser import HTMLParser

from placeinator.db.enums import JobType, SourceKind, WorkMode

# A real desktop browser UA: some hosts reject the default httpx/python UA
# outright regardless of robots.txt, which would look like a block when it is
# really just a naive user-agent filter.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 PlaceInatorBot/0.1"
)

_DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


def _can_fetch(parser: RobotFileParser, user_agent: str, url: str) -> bool:
    """Longest-matching-rule-wins robots.txt evaluation (RFC 9309), in place
    of ``RobotFileParser.can_fetch``'s own first-match-in-file-order logic.

    Verified against a real host during Indeed adapter development: its
    ``User-agent: *`` block opens with a blanket ``Allow: /`` before dozens of
    later, more specific ``Disallow:`` lines (``/viewjob``, ``/jobs/US/``,
    etc.). ``RobotFileParser.can_fetch`` walks rules in file order and
    returns the *first* match, so that opening ``Allow: /`` silently shadows
    every ``Disallow`` after it -- ``can_fetch`` reports paths as allowed that
    the file's own author, and every RFC 9309-compliant crawler, treats as
    disallowed. Since ADR 0003's entire compliance boundary rests on this
    check being correct, a first-match implementation is not good enough to
    build adapters on top of.
    """
    if getattr(parser, "allow_all", False):  # real attr, typeshed gap -- see below
        return True
    if getattr(parser, "disallow_all", False):  # real attr, typeshed gap -- see below
        return False

    entry = None
    for candidate in parser.entries:  # type: ignore[attr-defined]  # real attr, typeshed gap
        if candidate.applies_to(user_agent):
            entry = candidate
            break
    if entry is None:
        entry = parser.default_entry  # type: ignore[attr-defined]  # real attr, typeshed gap
    if entry is None:
        return True

    parsed = urlparse(unquote(url))
    normalized = quote(
        urlunparse(("", "", parsed.path, parsed.params, parsed.query, parsed.fragment))
    ) or "/"

    best_length = -1
    best_allowed = True
    for rule in entry.rulelines:
        matches = rule.path == "*" or normalized.startswith(rule.path)
        if matches and len(rule.path) > best_length:
            best_length = len(rule.path)
            best_allowed = rule.allowance
    return best_allowed


@dataclass(frozen=True)
class SearchQuery:
    """What the user is looking for. Not every adapter can use every field --
    ATS feeds are scoped to specific companies, not open keyword search."""

    keywords: str = ""
    location: str | None = None
    companies: tuple[str, ...] = ()


@dataclass(frozen=True)
class RawPosting:
    """One posting as an adapter found it, before it becomes a ``Job`` row.

    ``source_ref`` must be stable across repeated fetches of the same
    posting -- placeinator.jobs.service upserts on
    (source, source_ref) rather than inserting duplicates on every rescan.
    """

    source_ref: str
    company: str
    designation: str
    description: str
    url: str | None = None
    location: str | None = None
    work_mode: WorkMode = WorkMode.ANY
    job_type: JobType = JobType.UNKNOWN
    deadline: date | None = None
    posted_at: date | None = None


@dataclass(frozen=True)
class SourceBlocked:
    """Returned, never raised, when an adapter meets a wall it will not cross
    -- login, CAPTCHA, bot detection, or a robots.txt disallow. See
    ADR 0003: the UI's response to this is to offer manual paste, not to
    report a failure."""

    reason: str


FetchResult = list[RawPosting] | SourceBlocked


def is_blocked(result: FetchResult) -> bool:
    return isinstance(result, SourceBlocked)


class JobSource:
    """Base class for adapters. Subclasses implement ``fetch``; everything
    else here is the shared discipline (robots.txt, rate limiting) they
    should route their requests through rather than calling httpx directly."""

    source: SourceKind

    def __init__(self, *, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=_DEFAULT_TIMEOUT,
            follow_redirects=True,
        )
        self._robots_cache: dict[str, RobotFileParser] = {}
        self._rate_limiters: dict[str, RateLimiter] = {}

    def fetch(self, query: SearchQuery) -> FetchResult:  # pragma: no cover - abstract
        raise NotImplementedError

    def get(
        self, url: str, *, min_interval: float = 1.0, **kwargs: object
    ) -> httpx.Response | SourceBlocked:
        """The one path adapters should fetch through: robots.txt-gated,
        rate-limited per host, real UA. Returns SourceBlocked instead of
        raising when robots.txt disallows the path."""
        if not self._robots_allows(url):
            return SourceBlocked(f"robots.txt disallows {url}")

        self._rate_limiter_for(url, min_interval).wait()
        return self._client.get(url, **kwargs)  # type: ignore[arg-type]

    def _robots_allows(self, url: str) -> bool:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"

        parser = self._robots_cache.get(origin)
        if parser is None:
            parser = RobotFileParser()
            parser.set_url(f"{origin}/robots.txt")
            try:
                response = self._client.get(f"{origin}/robots.txt", timeout=5.0)
                if response.status_code >= 400:
                    # No robots.txt served -- RFC 9309 / RobotFileParser's own
                    # convention on a fetch failure is "presume allowed", not
                    # "disallow all". A 401/404 on the robots.txt path itself
                    # is not a statement about the path we actually want.
                    parser.allow_all = True  # type: ignore[attr-defined]  # real attr, typeshed gap
                else:
                    parser.parse(response.text.splitlines())
            except httpx.HTTPError:
                parser.allow_all = True  # type: ignore[attr-defined]  # real attr, typeshed gap
            self._robots_cache[origin] = parser

        return _can_fetch(parser, USER_AGENT, url)

    def _rate_limiter_for(self, url: str, min_interval: float) -> RateLimiter:
        host = urlparse(url).netloc
        limiter = self._rate_limiters.get(host)
        if limiter is None:
            limiter = RateLimiter(min_interval=min_interval)
            self._rate_limiters[host] = limiter
        return limiter

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> JobSource:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


@dataclass
class RateLimiter:
    """The simplest thing that works for a single-user desktop app making
    occasional requests: block until at least ``min_interval`` seconds have
    passed since the last request to this host. No token bucket burst
    allowance needed at this request volume."""

    min_interval: float
    _last_request: float = field(default=0.0, init=False)

    def wait(self) -> None:
        elapsed = time.monotonic() - self._last_request
        remaining = self.min_interval - elapsed
        if remaining > 0:
            time.sleep(remaining)
        self._last_request = time.monotonic()


def html_to_text(raw_html: str) -> str:
    """Strip markup and collapse whitespace -- chunk_job_description expects
    prose with real line breaks, not a wall of inline HTML. Shared across
    adapters (ats_feed, indeed) rather than each carrying its own copy."""
    if not raw_html:
        return ""
    tree = HTMLParser(raw_html)
    text = tree.text(separator="\n", deep=True) or ""
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def parse_epoch_ms(value: int | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromtimestamp(value / 1000, tz=UTC).date()
    except (ValueError, OSError, OverflowError):
        return None
