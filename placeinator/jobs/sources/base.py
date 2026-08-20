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


@dataclass(frozen=True)
class _RobotsRule:
    allow: bool
    path: str


_RobotsGroup = tuple[list[str], list[_RobotsRule]]


def _normalize_robots_path(value: str) -> str:
    """Applied to both robots.txt rule paths and the URLs checked against
    them, so prefix comparison in _can_fetch is apples-to-apples."""
    parsed = urlparse(unquote(value))
    normalized = quote(
        urlunparse(("", "", parsed.path, parsed.params, parsed.query, parsed.fragment))
    )
    return normalized or "/"


def _parse_robots_groups(text: str) -> list[_RobotsGroup]:
    """Groups a robots.txt file into (user-agent tokens, rules) per RFC 9309.

    Deliberately self-contained rather than routed through
    ``urllib.robotparser.RobotFileParser``: an earlier version of this
    function read that class's group-selection result off undocumented,
    private attributes (``entries``, ``default_entry``,
    ``RuleLine.path``/``.allowance``), which carry no stability guarantee --
    confirmed the hard way when they behaved differently between Python
    3.13.7 (this machine) and 3.13.15 (CI's windows-latest runner), silently
    breaking every disallow rule. Parsing the raw text ourselves means there
    is nothing left in a stdlib patch release that can break this again.
    """
    groups: list[_RobotsGroup] = []
    current_agents: list[str] = []
    current_rules: list[_RobotsRule] = []
    rule_seen = False

    def flush() -> None:
        if current_agents:
            groups.append((list(current_agents), list(current_rules)))

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field_name, _, value = line.partition(":")
        field_name = field_name.strip().lower()
        value = value.strip()

        if field_name == "user-agent":
            if rule_seen:
                # A User-agent line appearing after this group already has
                # rules starts a brand-new group (RFC 9309).
                flush()
                current_agents = []
                current_rules = []
                rule_seen = False
            current_agents.append(value.lower())
        elif field_name in ("allow", "disallow"):
            if not current_agents:
                continue  # a rule before any User-agent line applies to nothing
            rule_seen = True
            if field_name == "disallow" and value == "":
                continue  # an empty Disallow value means "nothing is disallowed"
            current_rules.append(
                _RobotsRule(allow=(field_name == "allow"), path=_normalize_robots_path(value))
            )

    flush()
    return groups


def _select_robots_rules(groups: list[_RobotsGroup], user_agent: str) -> list[_RobotsRule] | None:
    """The most specific matching group wins outright -- its rules are used
    alone, never merged with the wildcard group -- falling back to a "*"
    group, or to "allow everything" (``None``) if neither is present.
    Matches a robots.txt agent name against ours by substring, the same
    semantics ``urllib.robotparser.Entry.applies_to`` used."""
    ua_lower = user_agent.lower()
    best_rules: list[_RobotsRule] | None = None
    best_token_length = -1
    wildcard_rules: list[_RobotsRule] | None = None

    for agents, rules in groups:
        for agent in agents:
            if agent == "*":
                if wildcard_rules is None:
                    wildcard_rules = rules
            elif agent and agent in ua_lower and len(agent) > best_token_length:
                best_token_length = len(agent)
                best_rules = rules

    return best_rules if best_rules is not None else wildcard_rules


def _can_fetch(groups: list[_RobotsGroup], user_agent: str, url: str) -> bool:
    """Longest-matching-rule-wins robots.txt evaluation (RFC 9309) against
    pre-parsed groups -- see _parse_robots_groups for why this doesn't go
    through RobotFileParser. An empty rule set (no matching group at all)
    means allow, per RFC 9309's own default."""
    rules = _select_robots_rules(groups, user_agent)
    if rules is None:
        return True

    path = _normalize_robots_path(url)
    best_length = -1
    best_allowed = True
    for rule in rules:
        if path.startswith(rule.path) and len(rule.path) > best_length:
            best_length = len(rule.path)
            best_allowed = rule.allow
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
        self._robots_cache: dict[str, list[_RobotsGroup]] = {}
        self._rate_limiters: dict[str, RateLimiter] = {}

    def fetch(self, query: SearchQuery) -> FetchResult:  # pragma: no cover - abstract
        raise NotImplementedError

    def get(
        self, url: str, *, min_interval: float = 1.0, **kwargs: object
    ) -> httpx.Response | SourceBlocked:
        """The one path adapters should fetch through: robots.txt-gated,
        rate-limited per host, real UA. Returns SourceBlocked instead of
        raising -- both when robots.txt disallows the path and when the
        request itself fails at the transport layer.

        A timeout, DNS failure, or dropped connection is the network being
        unavailable, not a bug: ADR 0003's answer to an unreachable source is
        "offer manual paste", so it must not surface as a 500 the UI renders
        as an error. This is the only place adapters touch httpx, so catching
        here covers all four of them.
        """
        if not self._robots_allows(url):
            return SourceBlocked(f"robots.txt disallows {url}")

        self._rate_limiter_for(url, min_interval).wait()
        try:
            return self._client.get(url, **kwargs)  # type: ignore[arg-type]
        except httpx.HTTPError as exc:
            return SourceBlocked(f"could not reach {urlparse(url).netloc}: {exc}")

    def _robots_allows(self, url: str) -> bool:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"

        groups = self._robots_cache.get(origin)
        if groups is None:
            # A missing robots.txt (fetch failure, or a >=400 status on the
            # robots.txt path itself) is RFC 9309's own "presume allowed",
            # not "disallow all" -- an empty group list is exactly "allow
            # everything" to _can_fetch.
            try:
                response = self._client.get(f"{origin}/robots.txt", timeout=5.0)
                groups = [] if response.status_code >= 400 else _parse_robots_groups(response.text)
            except httpx.HTTPError:
                groups = []
            self._robots_cache[origin] = groups

        return _can_fetch(groups, USER_AGENT, url)

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
