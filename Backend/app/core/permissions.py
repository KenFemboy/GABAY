"""Authentication and role-based authorization dependencies.

Backend checks here are the real security boundary; the frontend only hides
navigation as a usability layer.
"""

from collections.abc import Callable

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import forbidden, not_authenticated
from app.core.security import TokenError, decode_access_token
from app.db.session import get_db
from app.models.user import Role, User

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise not_authenticated()

    try:
        payload = decode_access_token(credentials.credentials)
    except TokenError as exc:
        message = (
            "Your session has expired. Please sign in again."
            if exc.code == "token_expired"
            else "The access token is invalid."
        )
        raise not_authenticated(exc.code, message) from exc

    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError) as exc:
        raise not_authenticated("invalid_token", "The access token is invalid.") from exc

    user = db.get(User, user_id)
    if user is None or user.token_version != payload["ver"]:
        raise not_authenticated("invalid_token", "Your session is no longer valid. Please sign in again.")
    if not user.is_active:
        raise not_authenticated("account_inactive", "This account is inactive.")
    return user


def require_roles(*roles: Role) -> Callable[..., User]:
    """Dependency factory: allow only users whose role is in ``roles``."""
    allowed = {r.value for r in roles}

    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise forbidden()
        return user

    return dependency


require_admin = require_roles(Role.SYSTEM_ADMIN)
