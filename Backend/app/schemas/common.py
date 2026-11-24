"""Validators shared by several schema modules."""


def strip_required(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("This field is required.")
    return value


def strip_optional(value: object) -> object:
    """Before-validator: trim strings and turn blank input into None."""
    if isinstance(value, str):
        return value.strip() or None
    return value
