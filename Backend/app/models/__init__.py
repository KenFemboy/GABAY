"""Import every model here so Alembic autogenerate sees the full metadata."""

from app.models.user import Role, User, UserStatus

__all__ = ["Role", "User", "UserStatus"]
