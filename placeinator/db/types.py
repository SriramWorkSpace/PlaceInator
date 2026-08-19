"""Shared column types.

Declaring an enum column as a plain ``String`` looks correct and typechecks
correctly, but SQLAlchemy then hands back a bare ``str`` on load. Because these
are ``StrEnum`` members, ``==`` and ``match`` still behave, so the mistake hides
until something calls ``.name`` or ``isinstance`` and fails at runtime against a
green type check. Route every enum column through :func:`enum_column` instead.
"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import Enum
from sqlalchemy.types import TypeEngine


def enum_column(enum_cls: type[StrEnum], length: int = 32) -> TypeEngine:
    """A CHECK-constrained text column that round-trips as the enum type.

    ``native_enum=False`` keeps this portable and migration-friendly on SQLite,
    and ``values_callable`` stores the member *value* (``"remote"``) rather than
    its NAME (``"REMOTE"``), so raw SQL and JSON exports stay readable.

    An unrecognised value in the database raises ``LookupError`` on load rather
    than silently yielding a string no branch will match.
    """
    return Enum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=lambda cls: [member.value for member in cls],
        validate_strings=True,
    )
