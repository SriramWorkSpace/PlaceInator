"""Indeed keyword/location search.

ADR 0003 rates Indeed's expected coverage "Good — usable logged-out search
pages", and that held up under verification: the search results page at
``/jobs?q=...&l=...`` is a plain 200 for an unauthenticated request (no login
wall), and ``robots.txt``'s ``User-agent: *`` block permits it -- only
``/viewjob`` (the individual job-detail page) is disallowed for a generic
crawler, along with the country-path variants (``/jobs/US/`` etc.) this
adapter never constructs. That is precisely why this adapter never visits
``/viewjob``: it would be a real robots.txt violation, not a shortcut worth
taking, and the search page already carries everything RawPosting needs.

The results page embeds a JSON blob (``window.mosaic.providerData["mosaic-
provider-jobcards"]``) inside ``<script id="mosaic-data">`` -- the same kind
of structured, non-scraped data ats_feed.py reads from an API, just embedded
in HTML instead of served directly. No Playwright, no JS execution: this is
a plain server-rendered response. Every field name below was read from a
real live response during development (tests/fixtures/indeed/ holds a
trimmed, real one), not recalled from memory.

**Real limitation, not a bug**: the description is Indeed's own short
``snippet`` (one or two bullet points), not the full JD -- the full text
lives on ``/viewjob``, which robots.txt puts out of reach. Matching quality
against Indeed postings will reflect that; it is a ceiling this adapter
cannot raise without crossing the ADR 0003 boundary.
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import quote

from placeinator.db.enums import JobType, SourceKind, WorkMode
from placeinator.jobs.sources.base import (
    JobSource,
    RawPosting,
    SearchQuery,
    SourceBlocked,
    html_to_text,
    parse_epoch_ms,
)

_RATE_LIMIT_SECONDS = 3.0  # a single-user desktop app searching occasionally, not crawling
_SCRIPT_RE = re.compile(r'<script id="mosaic-data"[^>]*>(.*?)</script>', re.S)
_MARKER = 'window.mosaic.providerData["mosaic-provider-jobcards"]='
_JOB_KEY_RE = re.compile(r"[?&]jk=([a-f0-9]+)")

_JOB_TYPE_LABELS = {
    "full-time": "full_time",
    "part-time": "part_time",
    "contract": "contract",
    "internship": "internship",
}


class IndeedSource(JobSource):
    source = SourceKind.INDEED

    def fetch(self, query: SearchQuery) -> list[RawPosting] | SourceBlocked:
        url = (
            "https://www.indeed.com/jobs"
            f"?q={quote(query.keywords)}&l={quote(query.location or '')}"
        )
        response = self.get(url, min_interval=_RATE_LIMIT_SECONDS)
        if isinstance(response, SourceBlocked):
            return response
        if response.status_code != 200:
            return SourceBlocked(f"indeed returned {response.status_code}")

        results = _extract_results(response.text)
        if results is None:
            # The embedded data blob's shape changed -- exactly the
            # "selectors moved" case ADR 0003 calls out, not a login/CAPTCHA
            # wall. Reported the same way so the UI still offers manual paste.
            return SourceBlocked("indeed: could not find job listings in the response")

        postings = []
        for job in results:
            posting = _to_posting(job)
            if posting is not None:
                postings.append(posting)
        return postings


def _extract_results(html_text: str) -> list[dict[str, Any]] | None:
    match = _SCRIPT_RE.search(html_text)
    if not match:
        return None

    script = match.group(1)
    idx = script.find(_MARKER)
    if idx == -1:
        return None

    try:
        obj, _ = json.JSONDecoder().raw_decode(script, idx + len(_MARKER))
    except json.JSONDecodeError:
        return None

    try:
        results = obj["metaData"]["mosaicProviderJobCardsModel"]["results"]
    except (KeyError, TypeError):
        return None
    return results if isinstance(results, list) else None


def _to_posting(job: dict[str, Any]) -> RawPosting | None:
    job_key = _extract_job_key(job)
    if job_key is None:
        return None

    company = (job.get("company") or "").strip()
    designation = (job.get("displayTitle") or job.get("normTitle") or "").strip()
    if not company or not designation:
        return None

    return RawPosting(
        source_ref=f"indeed:{job_key}",
        company=company,
        designation=designation,
        description=html_to_text(job.get("snippet") or ""),
        url=f"https://www.indeed.com/viewjob?jk={job_key}",
        location=job.get("formattedLocation"),
        work_mode=_work_mode(job),
        job_type=_job_type(job),
        posted_at=parse_epoch_ms(job.get("pubDate")),
    )


def _extract_job_key(job: dict[str, Any]) -> str | None:
    for field_name in ("viewJobLink", "link"):
        value = job.get(field_name)
        if not value:
            continue
        match = _JOB_KEY_RE.search(value)
        if match:
            return match.group(1)
    return None


def _work_mode(job: dict[str, Any]) -> WorkMode:
    remote_model = job.get("remoteWorkModel") or {}
    return WorkMode.REMOTE if remote_model.get("type") == "REMOTE_ALWAYS" else WorkMode.ANY


def _job_type(job: dict[str, Any]) -> JobType:
    for attribute_group in job.get("taxonomyAttributes") or []:
        if attribute_group.get("label") != "job-types":
            continue
        labels = [a["label"].lower() for a in attribute_group.get("attributes") or []]
        # Multiple simultaneous job-type labels (e.g. "Contract or Full-time
        # or Part-time", genuinely seen on sponsored listings) are ambiguous
        # -- reporting one would be a guess, not a read.
        if len(labels) == 1 and labels[0] in _JOB_TYPE_LABELS:
            return JobType(_JOB_TYPE_LABELS[labels[0]])
    return JobType.UNKNOWN
