from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, in_list


class Role(StrEnum):
    SYSTEM_ADMIN = "system_admin"
    SNED_COORDINATOR = "sned_coordinator"
    TEACHER = "teacher"
    SCHOOL_HEAD = "school_head"  # School Head / SNED Focal


class UserStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"



class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(in_list("role", Role), name="ck_users_role"),
        CheckConstraint(in_list("status", UserStatus), name="ck_users_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    # Stored lower-cased; used as the login identifier.
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=UserStatus.ACTIVE.value
    )
    # Incremented on password change / deactivation so older tokens stop working.
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    @property
    def is_active(self) -> bool:
        return self.status == UserStatus.ACTIVE.value
