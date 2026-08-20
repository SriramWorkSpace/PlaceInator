"""Schema invariants that are easy to break and hard to notice.

Each test here corresponds to a defect that typechecks clean and only fails at
runtime, which is exactly the class of bug this project cannot afford in the
matching and placement pipelines.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from placeinator.db.base import Base
from placeinator.db.enums import ChunkKind, EventType, JobType, SourceKind, WorkMode
from placeinator.db.models import Job, Profile, Resume

# The `session` fixture lives in tests/conftest.py.


def test_enum_columns_round_trip_as_enums_not_strings(session):
    """A String column would return "remote", which == WorkMode.REMOTE but is not
    a WorkMode -- so isinstance and .name break while mypy stays green."""
    session.add(
        Job(
            company="Acme",
            designation="Backend Engineer",
            description="...",
            source=SourceKind.INDEED,
            work_mode=WorkMode.REMOTE,
            job_type=JobType.FULL_TIME,
        )
    )
    session.commit()
    session.expire_all()

    job = session.query(Job).one()
    assert isinstance(job.work_mode, WorkMode)
    assert isinstance(job.job_type, JobType)
    assert isinstance(job.source, SourceKind)
    assert job.work_mode.name == "REMOTE"


def test_enum_columns_store_the_value_not_the_member_name(session):
    """Raw SQL and JSON exports should read "remote", not "REMOTE"."""
    session.add(
        Job(company="Acme", designation="X", description="...", work_mode=WorkMode.REMOTE)
    )
    session.commit()

    stored = session.execute(sa.text("SELECT work_mode FROM job")).scalar_one()
    assert stored == "remote"


def test_corrupt_enum_value_fails_loudly(session):
    """An unrecognised value must raise, not silently yield a string that no
    branch in the scoring or placement pipelines will ever match."""
    session.add(Job(company="Acme", designation="X", description="..."))
    session.commit()
    session.execute(sa.text("UPDATE job SET work_mode = 'not_a_mode'"))
    session.commit()
    session.expire_all()

    with pytest.raises(LookupError):
        _ = session.query(Job).one().work_mode


def test_every_constraint_is_named(session):
    """SQLite migrations run in Alembic batch mode, which rebuilds tables and can
    only recreate constraints it can name. An anonymous constraint here means a
    broken or silently lossy migration later."""
    anonymous: list[str] = []
    for table in Base.metadata.tables.values():
        for constraint in table.constraints:
            if constraint.name is None or str(constraint.name) == "_unnamed_":
                anonymous.append(f"{table.name}.{type(constraint).__name__}")
        for index in table.indexes:
            if index.name is None:
                anonymous.append(f"{table.name}.Index")

    assert not anonymous, f"anonymous constraints will break batch migrations: {anonymous}"


def test_only_one_primary_resume_per_profile_at_the_db_level(session):
    """The partial unique index, not just service.py, is what must stop a
    profile from ever having two primary resumes -- app-layer bugs shouldn't
    be able to corrupt this invariant via a raw update or a race."""
    profile = Profile(full_name="Jane Doe", email="jane@example.com")
    session.add(profile)
    session.flush()

    session.add(
        Resume(
            profile=profile,
            label="A",
            version=1,
            source_format="tex",
            source_text="...",
            is_primary=True,
        )
    )
    session.flush()

    session.add(
        Resume(
            profile=profile,
            label="B",
            version=1,
            source_format="tex",
            source_text="...",
            is_primary=True,
        )
    )
    with pytest.raises(sa.exc.IntegrityError):
        session.flush()


def test_enum_values_are_stable_identifiers():
    """These strings are persisted, so renaming a value is a data migration.
    Pinning them makes that impossible to do by accident."""
    assert ChunkKind.PROJECT_BULLET.value == "project_bullet"
    assert EventType.TECHNICAL_ROUND.value == "technical_round"
    assert WorkMode.ONSITE.value == "onsite"
