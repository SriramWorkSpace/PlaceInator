"""Public ATS job-board APIs: Greenhouse, Lever, Ashby.

Small but stable and permitted (ADR 0003) -- these are official public APIs
meant for exactly this purpose, not scraped HTML. Unlike Indeed/LinkedIn/
Naukri this adapter cannot do open keyword search: each platform serves one
company's board at a time, so the query is a list of (platform, company slug)
pairs, not free-text keywords.

Every field name below was verified against a live response during
development, not recalled from memory -- see tests/fixtures/ats_feed/, which
holds real saved responses (trimmed to a couple of postings each), not
fabricated ones. The three schemas differ meaningfully:

* Greenhouse's list endpoint has no description; a second per-job request is
  needed to get one.
* Lever's ``descriptionPlain`` is genuinely plain text already.
* Ashby's ``descriptionHtml`` needs stripping to plain text.
"""

from __future__ import annotations

import html
import re
from datetime import UTC, date, datetime
from typing import Any, Literal

from selectolax.parser import HTMLParser

from placeinator.db.enums import SourceKind, WorkMode
from placeinator.jobs.sources.base import JobSource, RawPosting, SearchQuery, SourceBlocked

AtsPlatform = Literal["greenhouse", "lever", "ashby"]

_RATE_LIMIT_SECONDS = 1.0  # matches Lever's own stated Crawl-delay: 1


def _html_to_text(raw_html: str) -> str:
    """Strip markup and collapse whitespace -- chunk_job_description expects
    prose with real line breaks, not a wall of inline HTML."""
    if not raw_html:
        return ""
    tree = HTMLParser(raw_html)
    text = tree.text(separator="\n", deep=True) or ""
    return re.sub(r"\n{3,}", "\n\n", text).strip()


class AtsFeedSource(JobSource):
    source = SourceKind.ATS_FEED

    def __init__(self, *, max_postings_per_company: int = 40, **kwargs: object) -> None:
        """``max_postings_per_company`` caps how many postings one company
        contributes per fetch. Discovered live, not assumed: Stripe's
        Greenhouse board alone had 577 open postings, and Greenhouse's list
        endpoint carries no description -- each one needs its own detail
        request, rate-limited to Lever's own stated 1 req/sec courtesy. That
        is nearly ten minutes for one company, unprompted, the moment
        someone adds it to track. Applied uniformly across all three
        platforms for predictable behaviour, even though only Greenhouse's
        N+1 detail-fetch strictly requires it for speed."""
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._max_postings_per_company = max_postings_per_company

    def fetch(self, query: SearchQuery) -> list[RawPosting] | SourceBlocked:
        companies = query.companies
        if not companies:
            return []

        postings: list[RawPosting] = []
        for entry in companies:
            platform, slug = _parse_company_entry(entry)
            if platform == "greenhouse":
                result = self._fetch_greenhouse(slug)
            elif platform == "lever":
                result = self._fetch_lever(slug)
            else:
                result = self._fetch_ashby(slug)

            if isinstance(result, SourceBlocked):
                return result
            postings.extend(result)

        return postings

    # -- Greenhouse ------------------------------------------------------ #

    def _fetch_greenhouse(self, company_slug: str) -> list[RawPosting] | SourceBlocked:
        list_url = f"https://boards-api.greenhouse.io/v1/boards/{company_slug}/jobs"
        response = self.get(list_url, min_interval=_RATE_LIMIT_SECONDS)
        if isinstance(response, SourceBlocked):
            return response
        if response.status_code != 200:
            return SourceBlocked(f"greenhouse returned {response.status_code} for {company_slug}")

        postings = []
        jobs = response.json().get("jobs", [])[: self._max_postings_per_company]
        for job in jobs:
            detail_url = f"{list_url}/{job['id']}"
            description = self._fetch_greenhouse_description(detail_url)

            postings.append(
                RawPosting(
                    source_ref=f"greenhouse:{company_slug}:{job['id']}",
                    company=job.get("company_name") or company_slug,
                    designation=(job.get("title") or "").strip(),
                    description=description,
                    url=job.get("absolute_url"),
                    location=(job.get("location") or {}).get("name"),
                    posted_at=_parse_date(job.get("first_published")),
                )
            )
        return postings

    def _fetch_greenhouse_description(self, detail_url: str) -> str:
        """The list endpoint has no description; each job needs its own
        request. Failure here degrades to an empty description rather than
        failing the whole company's fetch over one bad detail request."""
        response = self.get(detail_url, min_interval=_RATE_LIMIT_SECONDS)
        if isinstance(response, SourceBlocked) or response.status_code != 200:
            return ""
        # Greenhouse double-escapes: the JSON string value is itself
        # HTML-entity-encoded HTML (verified live -- "content" holds literal
        # "&lt;p&gt;" text, not raw "<p>").
        content = response.json().get("content", "")
        return _html_to_text(html.unescape(content))

    # -- Lever ------------------------------------------------------------ #

    def _fetch_lever(self, company_slug: str) -> list[RawPosting] | SourceBlocked:
        url = f"https://api.lever.co/v0/postings/{company_slug}?mode=json"
        response = self.get(url, min_interval=_RATE_LIMIT_SECONDS)
        if isinstance(response, SourceBlocked):
            return response
        if response.status_code != 200:
            return SourceBlocked(f"lever returned {response.status_code} for {company_slug}")

        postings = []
        postings_data = response.json()[: self._max_postings_per_company]
        for job in postings_data:
            categories = job.get("categories") or {}
            description = job.get("descriptionPlain") or _html_to_text(job.get("description") or "")
            postings.append(
                RawPosting(
                    source_ref=f"lever:{company_slug}:{job['id']}",
                    company=company_slug,
                    designation=(job.get("text") or "").strip(),
                    description=description,
                    url=job.get("hostedUrl"),
                    location=categories.get("location"),
                    work_mode=_lever_work_mode(job),
                    posted_at=_parse_epoch_ms(job.get("createdAt")),
                )
            )
        return postings

    # -- Ashby -------------------------------------------------------------- #

    def _fetch_ashby(self, company_slug: str) -> list[RawPosting] | SourceBlocked:
        url = f"https://api.ashbyhq.com/posting-api/job-board/{company_slug}"
        response = self.get(url, min_interval=_RATE_LIMIT_SECONDS)
        if isinstance(response, SourceBlocked):
            return response
        if response.status_code != 200:
            return SourceBlocked(f"ashby returned {response.status_code} for {company_slug}")

        postings = []
        jobs = response.json().get("jobs", [])[: self._max_postings_per_company]
        for job in jobs:
            postings.append(
                RawPosting(
                    source_ref=f"ashby:{company_slug}:{job['id']}",
                    company=company_slug,
                    designation=(job.get("title") or "").strip(),
                    description=_html_to_text(job.get("descriptionHtml") or ""),
                    url=job.get("jobUrl"),
                    location=job.get("location"),
                    work_mode=WorkMode.REMOTE if job.get("isRemote") else WorkMode.ANY,
                    posted_at=_parse_date(job.get("publishedAt")),
                )
            )
        return postings


def _parse_company_entry(entry: str) -> tuple[AtsPlatform, str]:
    """Entries are "platform:slug", e.g. "greenhouse:stripe"."""
    platform, _, slug = entry.partition(":")
    if platform not in ("greenhouse", "lever", "ashby") or not slug:
        raise ValueError(f"expected 'platform:company-slug', got {entry!r}")
    return platform, slug  # type: ignore[return-value]


def _lever_work_mode(job: dict[str, Any]) -> WorkMode:
    workplace_type = (job.get("workplaceType") or "").lower()
    if workplace_type == "remote":
        return WorkMode.REMOTE
    if workplace_type == "hybrid":
        return WorkMode.HYBRID
    if workplace_type == "onsite":
        return WorkMode.ONSITE
    return WorkMode.ANY


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _parse_epoch_ms(value: int | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromtimestamp(value / 1000, tz=UTC).date()
    except (ValueError, OSError, OverflowError):
        return None
