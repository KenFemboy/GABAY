from enum import StrEnum

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def in_list(column: str, values: type[StrEnum]) -> str:
    """SQL for a CHECK constraint that limits ``column`` to the enum's values."""
    quoted = ", ".join(f"'{v.value}'" for v in values)
    return f"{column} IN ({quoted})"
