from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.models.user import Role, UserStatus
from app.schemas.common import strip_required

PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_LENGTH = 128


def normalize_email(value: str) -> str:
    value = value.strip().lower()
    local, sep, domain = value.partition("@")
    if not sep or not local or "." not in domain or " " in value:
        raise ValueError("Enter a valid email address.")
    return value


def validate_new_password(value: str) -> str:
    if len(value) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters.")
    if len(value) > PASSWORD_MAX_LENGTH:
        raise ValueError(f"Password must be at most {PASSWORD_MAX_LENGTH} characters.")
    return value


Email = Annotated[str, Field(max_length=255), AfterValidator(normalize_email)]
NewPassword = Annotated[str, AfterValidator(validate_new_password)]
PersonName = Annotated[str, Field(max_length=150), AfterValidator(strip_required)]


class UserRead(BaseModel):
    """Safe user fields returned to the frontend (never the password hash)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    role: Role
    status: UserStatus
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime


class UserCreate(BaseModel):
    name: PersonName
    email: Email
    password: NewPassword
    role: Role


class UserUpdate(BaseModel):
    name: PersonName | None = None
    email: Email | None = None
    role: Role | None = None
    status: UserStatus | None = None
    # Admin password reset; the user should change it after signing in.
    password: NewPassword | None = None


class UserBrief(BaseModel):
    """Minimal user info for pickers (for example assigning a teacher)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class UserList(BaseModel):
    items: list[UserRead]
    total: int
