"""SQLite engine and session management.

Python owns the database outright — the Rust shell never opens it — so there is
exactly one writer and one migration path.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from placeinator.settings import get_settings

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _configure_sqlite(dbapi_conn, _record) -> None:
    """WAL keeps reads non-blocking while a background scan writes."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


def get_engine() -> Engine:
    global _engine, _SessionLocal
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(
            f"sqlite:///{settings.db_path}",
            echo=False,
            future=True,
        )
        event.listen(_engine, "connect", _configure_sqlite)
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope; commits on success, rolls back on failure."""
    get_engine()
    assert _SessionLocal is not None
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    """FastAPI dependency variant of :func:`session_scope`."""
    with session_scope() as session:
        yield session


def reset_engine() -> None:
    """Test-only: drop the cached engine and session factory.

    Production never calls this -- one process has exactly one database for
    its whole life, set once from Settings.db_path. Tests that construct
    multiple app lifetimes in the same process (e.g. one per test function,
    each with its own temp data dir) must call this alongside
    ``get_settings.cache_clear()``, or every test after the first silently
    reuses the first test's SQLite file instead of its own.
    """
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
