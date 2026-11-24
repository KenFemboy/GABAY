from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, in_list
from app.models.user import User


class LearnerStatus(StrEnum):
    """Learners are never deleted; their status changes instead."""

    ACTIVE = "active"
    TRANSFERRED = "transferred"
    GRADUATED = "graduated"
    INACTIVE = "inactive"


class Sex(StrEnum):
    MALE = "male"
    FEMALE = "female"


class GradeLevel(StrEnum):
    KINDERGARTEN = "K"
    GRADE_1 = "1"
    GRADE_2 = "2"
    GRADE_3 = "3"
    GRADE_4 = "4"
    GRADE_5 = "5"
    GRADE_6 = "6"
    GRADE_7 = "7"
    GRADE_8 = "8"
    GRADE_9 = "9"
    GRADE_10 = "10"
    GRADE_11 = "11"
    GRADE_12 = "12"
    NON_GRADED = "NG"


class Learner(Base):
    """The central record: every later module row carries a ``learner_id``."""

    __tablename__ = "learners"
    __table_args__ = (
        CheckConstraint(in_list("status", LearnerStatus), name="ck_learners_status"),
        CheckConstraint(in_list("sex", Sex), name="ck_learners_sex"),
        CheckConstraint(in_list("grade_level", GradeLevel), name="ck_learners_grade_level"),
        Index("ix_learners_name", "last_name", "first_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Stored upper-cased so uniqueness is case-insensitive.
    learner_code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    middle_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    birth_date: Mapped[date] = mapped_column(Date, nullable=False)
    sex: Mapped[str] = mapped_column(String(8), nullable=False)
    grade_level: Mapped[str] = mapped_column(String(4), nullable=False)
    section: Mapped[str] = mapped_column(String(50), nullable=False)
    # Format "2025-2026".
    school_year: Mapped[str] = mapped_column(String(9), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=LearnerStatus.ACTIVE.value, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    @property
    def full_name(self) -> str:
        parts = [self.first_name, self.middle_name, self.last_name]
        return " ".join(p for p in parts if p)


class LearnerAssignment(Base):
    """Links a Teacher to a learner for one school year."""

    __tablename__ = "learner_assignments"
    __table_args__ = (
        UniqueConstraint("learner_id", "user_id", "school_year", name="uq_learner_assignments"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    learner_id: Mapped[int] = mapped_column(
        ForeignKey("learners.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    school_year: Mapped[str] = mapped_column(String(9), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped[User] = relationship(lazy="joined")

    @property
    def user_name(self) -> str:
        return self.user.name
