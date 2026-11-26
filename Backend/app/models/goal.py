"""Goal bank (Stage 7): taxonomy, versioned goals, usage tracking and embeddings.

* ``Goal`` is the identity (code + status); its wording lives in ``GoalVersion``.
* Editing a goal whose current version is USED (has ``GoalUsage`` rows, e.g.
  in an IEP) creates a new version; unused versions are edited in place.
* ``GoalEmbedding`` holds one vector per (goal version, model) - the unique
  constraint makes reindexing safe to repeat.
"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, in_list
from app.models.user import User


class GoalStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class MeasurementMethod(StrEnum):
    PERCENT_ACCURACY = "percent_accuracy"
    TRIALS = "trials"
    FREQUENCY = "frequency"
    DURATION = "duration"
    RATE = "rate"
    RUBRIC = "rubric"
    CHECKLIST = "checklist"


class TargetUnit(StrEnum):
    PERCENT = "percent"
    TRIALS = "trials"
    COUNT = "count"
    MINUTES = "minutes"
    WPM = "wpm"  # words per minute
    LEVEL = "level"  # rubric level


class GradeBand(StrEnum):
    K_3 = "K-3"
    G4_6 = "4-6"
    G7_10 = "7-10"
    G11_12 = "11-12"
    ANY = "any"


class GoalDomain(Base):
    __tablename__ = "goal_domains"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Matches FindingDomain values (Stage 6) so findings and goals can be joined.
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    skills: Mapped[list["GoalSkill"]] = relationship(
        back_populates="domain", order_by="(GoalSkill.sort_order, GoalSkill.id)", lazy="selectin"
    )


class GoalSkill(Base):
    __tablename__ = "goal_skills"
    __table_args__ = (UniqueConstraint("domain_id", "code", name="uq_goal_skills_domain_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    domain_id: Mapped[int] = mapped_column(ForeignKey("goal_domains.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(48), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    domain: Mapped[GoalDomain] = relationship(back_populates="skills")


class Goal(Base):
    __tablename__ = "goals"
    __table_args__ = (CheckConstraint(in_list("status", GoalStatus), name="ck_goals_status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=GoalStatus.DRAFT.value)
    current_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("goal_versions.id", use_alter=True, name="fk_goals_current_version")
    )
    # NULL = loaded from the starter set.
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    current_version: Mapped["GoalVersion | None"] = relationship(
        foreign_keys=[current_version_id], lazy="joined", post_update=True
    )
    versions: Mapped[list["GoalVersion"]] = relationship(
        foreign_keys="GoalVersion.goal_id",
        back_populates="goal",
        order_by="GoalVersion.version_number.desc()",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    creator: Mapped[User | None] = relationship(foreign_keys=[created_by], lazy="joined")

    @property
    def created_by_name(self) -> str:
        return self.creator.name if self.creator else "Starter set"


class GoalVersion(Base):
    __tablename__ = "goal_versions"
    __table_args__ = (
        UniqueConstraint("goal_id", "version_number", name="uq_goal_versions_number"),
        CheckConstraint(in_list("measurement_method", MeasurementMethod), name="ck_goal_versions_method"),
        CheckConstraint(in_list("target_unit", TargetUnit), name="ck_goal_versions_unit"),
        CheckConstraint(in_list("grade_band", GradeBand), name="ck_goal_versions_grade_band"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    goal_id: Mapped[int] = mapped_column(
        ForeignKey("goals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    domain_id: Mapped[int] = mapped_column(ForeignKey("goal_domains.id"), nullable=False)
    skill_id: Mapped[int] = mapped_column(ForeignKey("goal_skills.id"), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    measurement_method: Mapped[str] = mapped_column(String(24), nullable=False)
    target_value: Mapped[float] = mapped_column(Float, nullable=False)
    target_unit: Mapped[str] = mapped_column(String(16), nullable=False)
    criterion: Mapped[str | None] = mapped_column(String(300))
    grade_band: Mapped[str] = mapped_column(String(8), nullable=False, default=GradeBand.ANY.value)
    change_note: Mapped[str | None] = mapped_column(String(300))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    goal: Mapped[Goal] = relationship(foreign_keys=[goal_id], back_populates="versions")
    domain: Mapped[GoalDomain] = relationship(lazy="joined")
    skill: Mapped[GoalSkill] = relationship(lazy="joined")
    creator: Mapped[User | None] = relationship(foreign_keys=[created_by], lazy="joined")
    usages: Mapped[list["GoalUsage"]] = relationship(lazy="selectin", viewonly=True)

    @property
    def created_by_name(self) -> str:
        return self.creator.name if self.creator else "Starter set"

    @property
    def usage_count(self) -> int:
        return len(self.usages)


class GoalUsage(Base):
    """A goal version referenced elsewhere (e.g. an IEP). Makes that version immutable."""

    __tablename__ = "goal_usages"
    __table_args__ = (
        UniqueConstraint("goal_version_id", "usage_type", "reference_id", name="uq_goal_usages_ref"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    goal_version_id: Mapped[int] = mapped_column(
        ForeignKey("goal_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    usage_type: Mapped[str] = mapped_column(String(32), nullable=False)
    reference_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class GoalEmbedding(Base):
    __tablename__ = "goal_embeddings"
    __table_args__ = (
        UniqueConstraint("goal_version_id", "model", name="uq_goal_embeddings_version_model"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    goal_version_id: Mapped[int] = mapped_column(
        ForeignKey("goal_versions.id", ondelete="CASCADE"), nullable=False
    )
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    # SHA-256 of the exact text that was embedded; a mismatch means "stale".
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    dims: Mapped[int] = mapped_column(Integer, nullable=False)
    vector: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)  # float32, L2-normalised
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
