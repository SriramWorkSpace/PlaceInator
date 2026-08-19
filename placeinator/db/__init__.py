"""Data and state layer.

Python owns SQLite outright -- the Rust shell never opens it -- so there is
exactly one writer, one schema, and one migration path.

Two invariants that are easy to break and hard to notice:

* **Alembic is the only thing that creates or alters schema.** ``create_all`` is
  never called, including on first run. See
  docs/decisions.md#adr-0004--alembic-is-the-sole-owner-of-database-schema.
* **Enum columns go through** :func:`placeinator.db.types.enum_column`, never a
  bare ``String``. A ``String`` column returns a plain ``str`` that still
  compares equal to its ``StrEnum`` member, so the mistake hides until something
  calls ``.name`` or ``isinstance`` and fails at runtime with a green type check.
"""
