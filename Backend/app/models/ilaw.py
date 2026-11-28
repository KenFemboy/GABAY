"""ILAW: daily learning activity log, aligned with the active IEP's goals (Stage 10).

``ilaw_entries`` - one activity done with a learner on a date. The unique key
(learner, date, normalised title) prevents duplicate entries.

``ilaw_alignments`` - links between an entry and IEP goals: suggested by the
embedding model (with score, rank and model version) or added by hand, then
confirmed or rejected by a teacher. One row per (entry, goal).
"""

from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, in_list
from app.models.iep import IepGoal
from app.models.user import User


class AlignmentStatus(StrEnum):
    SUGGESTED = "suggested"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class AlignmentSource(StrEnum):
    SUGGESTED = "suggested"
    MANUAL = "manual"


class IlawEntry(Base):
    __tablename__ = "ilaw_entries"
    __table_args__ = (
        UniqueConstraint("learner_id", "activity_date", "title_key", name="uq_ilaw_entries_learner_date_title"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    learner_id: Mapped[int] = mapped_column(
        ForeignKey("learners.id", ondelete="CASCADE"), nullable=False, index=True
    )
    iep_id: Mapped[int] = mapped_column(ForeignKey("ieps.id"), nullable=False)
    activity_date: Mapped[date] = mapped_column(Date, nullable=False)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    # Lower-cased, whitespace-collapsed title: the duplicate key.
    title_key: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    materials: Mapped[str | None] = mapped_column(Text)
    learner_response: Mapped[str | None] = mapped_column(Text)
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    creator: Mapped[User] = relationship(lazy="joined")
    alignments: Mapped[list["IlawAlignment"]] = relationship(
        back_populates="entry",
        cascade="all, delete-orphan",
        order_by="(IlawAlignment.rank.is_(None), IlawAlignment.rank, IlawAlignment.id)",
        lazy="selectin",
    )

    @property
    def created_by_name(self) -> str:
        return self.creator.name


class IlawAlignment(Base):
    __tablename__ = "ilaw_alignments"
    __table_args__ = (
        UniqueConstraint("entry_id", "iep_goal_id", name="uq_ilaw_alignments_entry_goal"),
        CheckConstraint(in_list("status", AlignmentStatus), name="ck_ilaw_alignments_status"),
        CheckConstraint(in_list("source", AlignmentSource), name="ck_ilaw_alignments_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_id: Mapped[int] = mapped_column(
        ForeignKey("ilaw_entries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    iep_goal_id: Mapped[int] = mapped_column(ForeignKey("iep_goals.id", ondelete="CASCADE"), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=AlignmentStatus.SUGGESTED.value)
    score: Mapped[float | None] = mapped_column(Float)
    rank: Mapped[int | None] = mapped_column(Integer)
    model_version: Mapped[str | None] = mapped_column(String(160))
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    entry: Mapped[IlawEntry] = relationship(back_populates="alignments")
    goal: Mapped[IepGoal] = relationship(lazy="joined")
    decider: Mapped[User | None] = relationship(foreign_keys=[decided_by], lazy="joined")

    @property
    def decided_by_name(self) -> str | None:
        return self.decider.name if self.decider else None
