"""Progress monitoring records (Stage 11).

One row = one piece of evidence about a learner: a measured data point for an
IEP goal (probe, work sample, test), an observation, or a grade. Values linked
to a goal use that goal's unit, so they can be charted against its baseline
and target.
"""

from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, in_list
from app.models.iep import IepGoal
from app.models.user import User


class EvidenceType(StrEnum):
    PROBE = "probe"  # data collection / trial for a goal
    WORK_SAMPLE = "work_sample"
    TEST = "test"
    OBSERVATION = "observation"
    GRADE = "grade"


class ProgressUnit(StrEnum):
    PERCENT = "percent"
    TRIALS = "trials"
    COUNT = "count"
    MINUTES = "minutes"
    WPM = "wpm"
    LEVEL = "level"
    GRADE = "grade"


class GradingPeriod(StrEnum):
    Q1 = "Q1"
    Q2 = "Q2"
    Q3 = "Q3"
    Q4 = "Q4"
    FINAL = "final"


class ProgressRecord(Base):
    __tablename__ = "progress_records"
    __table_args__ = (
        CheckConstraint(in_list("evidence_type", EvidenceType), name="ck_progress_records_type"),
        CheckConstraint(f"unit IS NULL OR {in_list('unit', ProgressUnit)}", name="ck_progress_records_unit"),
        CheckConstraint(
            f"grading_period IS NULL OR {in_list('grading_period', GradingPeriod)}",
            name="ck_progress_records_period",
        ),
        Index("ix_progress_records_goal_date", "iep_goal_id", "recorded_on"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    learner_id: Mapped[int] = mapped_column(
        ForeignKey("learners.id", ondelete="CASCADE"), nullable=False, index=True
    )
    iep_id: Mapped[int] = mapped_column(ForeignKey("ieps.id"), nullable=False)
    iep_goal_id: Mapped[int | None] = mapped_column(ForeignKey("iep_goals.id", ondelete="CASCADE"))
    ilaw_entry_id: Mapped[int | None] = mapped_column(ForeignKey("ilaw_entries.id", ondelete="SET NULL"))
    evidence_type: Mapped[str] = mapped_column(String(16), nullable=False)
    value: Mapped[float | None] = mapped_column(Float)
    out_of: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(16))
    subject: Mapped[str | None] = mapped_column(String(60))
    grading_period: Mapped[str | None] = mapped_column(String(8))
    recorded_on: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    goal: Mapped[IepGoal | None] = relationship(lazy="joined")
    creator: Mapped[User] = relationship(lazy="joined")

    @property
    def created_by_name(self) -> str:
        return self.creator.name
