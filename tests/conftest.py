"""Shared test fixtures.

Layout:

* ``tests/unit/`` -- in-process and fast; no subprocesses, no network, no disk
  beyond tmp paths.
* ``tests/integration/`` -- real I/O. The handshake test deliberately spawns an
  actual subprocess, because an in-process test cannot catch a stray write to
  stdout corrupting the startup protocol.
* ``tests/fixtures/`` -- golden files (resumes, JDs, placement sheets, scraped
  HTML) that the M1-M4 suites assert against.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from placeinator.db.base import Base

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def session() -> Iterator[Session]:
    """An in-memory database with the full schema.

    Uses ``create_all`` rather than Alembic on purpose: this fixture tests the
    *models*, and going through migrations would make every schema test depend
    on migration correctness too. Application code must never do this -- see
    docs/decisions.md#adr-0004--alembic-is-the-sole-owner-of-database-schema.
    """
    engine = sa.create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Where the sidecar must be launched from."""
    return REPO_ROOT


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES
