"""Programmatic Alembic upgrade.

A packaged sidecar has no shell and no `alembic` entry point, so the app has to
drive migrations itself on startup. Resolving the config relative to this file
keeps it working from a PyInstaller bundle, where the CWD is arbitrary.
"""

from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config

log = logging.getLogger(__name__)

# placeinator/db/migrate.py -> repo root (or the bundle root once frozen)
_ROOT = Path(__file__).resolve().parents[2]


def _alembic_config() -> Config:
    config = Config(str(_ROOT / "alembic.ini"))
    # alembic.ini stores a relative script_location, which breaks the moment the
    # process starts anywhere but the repo root.
    config.set_main_option("script_location", str(_ROOT / "migrations"))
    return config


def upgrade_to_head() -> None:
    """Bring the database up to the newest revision. Safe to call on every boot."""
    log.info("running database migrations")
    command.upgrade(_alembic_config(), "head")
    log.info("database is at head")
