"""placeinator.jobs.service.search_jobs -- the dispatch layer behind
``POST /api/jobs/search``.

This is the only discovery path wired to a UI control, and it had no test at
all until this file. The adapters themselves are covered per-source
(test_indeed / test_linkedin / test_naukri); what is exercised here is the
dispatch table, the ``SourceBlocked`` passthrough, and adapter lifetime.

The successful-upsert half of this function needs the real embedding model
(``_apply_requirements`` embeds every requirement line), so it lives in
tests/integration/test_jobs_search_api.py under the ``model`` marker rather
than here.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from placeinator.db.enums import SourceKind
from placeinator.jobs.service import search_jobs
from placeinator.jobs.sources.base import FetchResult, JobSource, SearchQuery, SourceBlocked


class _BlockedSource(JobSource):
    """Stands in for linkedin/naukri: blocked, and records that it was
    closed so adapter lifetime is observable."""

    source = SourceKind.LINKEDIN
    closed = False

    def fetch(self, query: SearchQuery) -> FetchResult:
        return SourceBlocked("blocked for the usual reason")

    def close(self) -> None:
        type(self).closed = True
        super().close()


def test_source_blocked_is_returned_not_raised(session: Session, monkeypatch):
    """ADR 0003's central rule at the service boundary: a blocked source is a
    value the UI can explain, never an exception."""
    monkeypatch.setattr(
        "placeinator.jobs.service._SEARCH_SOURCES",
        {SourceKind.LINKEDIN: _BlockedSource},
    )

    result = search_jobs(session, SourceKind.LINKEDIN, SearchQuery(keywords="backend"))

    assert isinstance(result, SourceBlocked)
    assert result.reason == "blocked for the usual reason"


def test_a_blocked_source_creates_no_jobs(session: Session, monkeypatch):
    monkeypatch.setattr(
        "placeinator.jobs.service._SEARCH_SOURCES",
        {SourceKind.LINKEDIN: _BlockedSource},
    )

    search_jobs(session, SourceKind.LINKEDIN, SearchQuery(keywords="backend"))

    from placeinator.jobs.service import list_jobs

    assert list_jobs(session) == []


def test_the_adapter_is_closed_even_though_the_fetch_was_blocked(session: Session, monkeypatch):
    """Each adapter owns an httpx.Client, so a search that ends in
    SourceBlocked must still release it rather than leaking a connection pool
    per search."""
    _BlockedSource.closed = False
    monkeypatch.setattr(
        "placeinator.jobs.service._SEARCH_SOURCES",
        {SourceKind.LINKEDIN: _BlockedSource},
    )

    search_jobs(session, SourceKind.LINKEDIN, SearchQuery(keywords="backend"))

    assert _BlockedSource.closed is True


@pytest.mark.parametrize("source", [SourceKind.MANUAL, SourceKind.ATS_FEED])
def test_a_source_that_is_not_keyword_searchable_raises_a_clear_error(
    session: Session, source: SourceKind
):
    """``manual`` has no remote to search and ``ats_feed`` is company-scoped
    (it goes through sync_ats_feed). Previously both produced a bare KeyError,
    which surfaces as an opaque 500."""
    with pytest.raises(ValueError, match="not keyword-searchable"):
        search_jobs(session, source, SearchQuery(keywords="backend"))
