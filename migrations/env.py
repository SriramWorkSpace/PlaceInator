"""Alembic environment.

The database URL comes from placeinator.settings rather than alembic.ini, so migrations
always target the same per-user data directory the running app uses.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context

# Importing the models registers every mapper on Base.metadata; without it
# autogenerate would see an empty schema and cheerfully emit "drop everything".
import placeinator.db.models  # noqa: F401
from placeinator.db.base import Base
from placeinator.db.session import get_engine

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    engine = get_engine()
    context.configure(
        url=engine.url.render_as_string(hide_password=False),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # SQLite cannot ALTER most things in place; batch mode rewrites the
        # table instead of failing halfway through a migration.
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = get_engine()
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
