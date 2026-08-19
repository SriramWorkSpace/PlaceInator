# ADR 0004 — Alembic is the sole owner of database schema

- **Status:** Accepted
- **Date:** 2026-08-19
- **Supersedes:** the initial `create_all` bootstrap

## Context

The first implementation called `Base.metadata.create_all()` on startup while Alembic
was also configured, with the intention that Alembic would "take over from M1 onward".

This is a common and dangerous arrangement. A fresh install builds tables via
`create_all` and leaves `alembic_version` **empty**. The first real migration then
tries to create tables that already exist — failing on any machine that has run the
app before, while passing on a clean one. The bug is environment-dependent and
invisible during development.

A second problem compounds it: SQLite cannot `ALTER` most constraints, so Alembic runs
in **batch mode**, rebuilding each table and recreating its constraints. Batch mode can
only recreate constraints it can *name*, and SQLAlchemy's default is anonymous.

## Decision

**Alembic is the only thing that ever creates or alters schema.** `create_all` is not
called anywhere, including in the startup path.

- `placeinator/db/migrate.py::upgrade_to_head` runs on every sidecar boot.
- It resolves `alembic.ini` and `script_location` relative to the package file, not the
  CWD, so it also works inside a PyInstaller bundle.
- `alembic.ini` deliberately leaves `sqlalchemy.url` **unset**; `migrations/env.py`
  takes the URL from `placeinator.settings`, so the CLI and the running app can never
  target different databases.
- `migrations/env.py` sets `render_as_batch=True`, plus `compare_type` and
  `compare_server_default` for meaningful autogenerate diffs.
- `Base.metadata` carries a `NAMING_CONVENTION` for `ix`/`uq`/`ck`/`fk`/`pk`, so every
  constraint is nameable by batch mode.

## Consequences

- Fresh installs and upgraded installs converge on identical schema, always.
- Schema changes require a migration; there is no path that silently creates tables.
  After editing a model:

  ```bash
  .venv/Scripts/python.exe -m alembic revision --autogenerate -m "what changed"
  ```

- `alembic check` becomes a meaningful CI-able assertion that models and migrations
  have not drifted.
- Generated migrations under `migrations/versions/` are excluded from `ruff` — they are
  machine output, and reformatting them only creates churn against regenerated files.
- A test (`test_every_constraint_is_named`) fails if an anonymous constraint is ever
  introduced, because the cost of finding that out during a future migration is far
  higher than the cost of the test.
