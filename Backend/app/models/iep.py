"""Individualized Education Program (Stage 9).

Each row in ``ieps`` is one VERSION of a learner's plan for a school year:
v1 is created as a draft; once finalized it is read-only; an amendment copies
it into v(N+1) as a new draft, and finalizing that supersedes the old version.

Findings and goals are SNAPSHOTS (copied text), so later re-extraction, goal
bank edits or new matching runs never change a saved IEP.
"""

from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
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
from app.models.user import User


class IepStatus(StrEnum):
    DRAFT = "draft"
    FINALIZED = "finalized"
    SUPERSEDED = "superseded"


class IepGoalSource(StrEnum):
    ACCEPTED_RECOMMENDATION = "accepted_recommendation"  # from Stage 8 goal suggestions
    GOAL_BANK = "goal_bank"  # picked directly from the goal bank
    CUSTOM = "custom"  # written for this IEP only


class Iep(Base):
    __tablename__ = "ieps"
    __table_args__ = (
        UniqueConstraint("learner_id", "school_year", "version_number", name="uq_ieps_learner_year_version"),
        CheckConstraint(in_list("status", IepStatus), name="ck_ieps_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    learner_id: Mapped[int] = mapped_column(
        ForeignKey("learners.id", ondelete="CASCADE"), nullable=False, index=True
    )
    school_year: Mapped[str] = mapped_column(String(9), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=IepStatus.DRAFT.value)
    amends_iep_id: Mapped[int | None] = mapped_column(ForeignKey("ieps.id", ondelete="SET NULL"))
    amendment_reason: Mapped[str | None] = mapped_column(Text)

    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    annual_review_date: Mapped[date | None] = mapped_column(Date)
    accommodations: Mapped[str | None] = mapped_column(Text)
    services: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    # [{"name": "...", "role": "..."}] - printed in the signature block.
    team_members: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    finalized_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    creator: Mapped[User] = relationship(foreign_keys=[created_by], lazy="joined")
    finalizer: Mapped[User | None] = relationship(foreign_keys=[finalized_by], lazy="joined")
    findings: Mapped[list["IepFinding"]] = relationship(
        back_populates="iep",
        cascade="all, delete-orphan",
        order_by="(IepFinding.position, IepFinding.id)",
        lazy="selectin",
    )
    goals: Mapped[list["IepGoal"]] = relationship(
        back_populates="iep",
        cascade="all, delete-orphan",
        order_by="(IepGoal.position, IepGoal.id)",
        lazy="selectin",
    )

    @property
    def created_by_name(self) -> str:
        return self.creator.name

    @property
    def finalized_by_name(self) -> str | None:
        return self.finalizer.name if self.finalizer else None

    @property
    def read_only(self) -> bool:
        return self.status != IepStatus.DRAFT.value


class IepFinding(Base):
    __tablename__ = "iep_findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    iep_id: Mapped[int] = mapped_column(ForeignKey("ieps.id", ondelete="CASCADE"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(32))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_finding_id: Mapped[int | None] = mapped_column(
        ForeignKey("extraction_findings.id", ondelete="SET NULL")
    )

    iep: Mapped[Iep] = relationship(back_populates="findings")


class IepGoal(Base):
    __tablename__ = "iep_goals"
    __table_args__ = (CheckConstraint(in_list("source", IepGoalSource), name="ck_iep_goals_source"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    iep_id: Mapped[int] = mapped_column(ForeignKey("ieps.id", ondelete="CASCADE"), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    goal_recommendation_id: Mapped[int | None] = mapped_column(
        ForeignKey("goal_recommendations.id", ondelete="SET NULL")
    )
    goal_id: Mapped[int | None] = mapped_column(ForeignKey("goals.id", ondelete="SET NULL"))
    goal_version_id: Mapped[int | None] = mapped_column(ForeignKey("goal_versions.id", ondelete="SET NULL"))
    addresses_finding_id: Mapped[int | None] = mapped_column(
        ForeignKey("iep_findings.id", ondelete="SET NULL")
    )

    domain: Mapped[str | None] = mapped_column(String(32))
    skill_name: Mapped[str | None] = mapped_column(String(120))
    goal_code: Mapped[str | None] = mapped_column(String(16))
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    measurement_method: Mapped[str | None] = mapped_column(String(24))
    baseline: Mapped[str | None] = mapped_column(Text)
    baseline_value: Mapped[float | None] = mapped_column(Float)
    target_value: Mapped[float | None] = mapped_column(Float)
    target_unit: Mapped[str | None] = mapped_column(String(16))
    criterion: Mapped[str | None] = mapped_column(String(300))
    responsible_staff: Mapped[str | None] = mapped_column(String(500))
    start_date: Mapped[date | None] = mapped_column(Date)
    target_date: Mapped[date | None] = mapped_column(Date)
    # ISO date strings: progress-review checkpoints (used by progress monitoring).
    review_dates: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    match_score: Mapped[float | None] = mapped_column(Float)

    iep: Mapped[Iep] = relationship(back_populates="goals")
