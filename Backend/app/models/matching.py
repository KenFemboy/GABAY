"""Semantic goal matching (Stage 8): need embeddings, matching runs, recommendations."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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
from app.db.vector import EMBEDDING_DIMS, EmbeddingVector
from app.models.extraction import ExtractionFinding
from app.models.goal import Goal, GoalVersion
from app.models.user import User


class RecommendationStatus(StrEnum):
    SUGGESTED = "suggested"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class RecommendationSource(StrEnum):
    MATCHED = "matched"
    MANUAL = "manual"


class NeedEmbedding(Base):
    """Vector for one approved need finding (findings never change once approved)."""

    __tablename__ = "need_embeddings"
    __table_args__ = (UniqueConstraint("finding_id", "model", name="uq_need_embeddings_finding_model"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    finding_id: Mapped[int] = mapped_column(
        ForeignKey("extraction_findings.id", ondelete="CASCADE"), nullable=False
    )
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding: Mapped[object] = mapped_column(EmbeddingVector(EMBEDDING_DIMS), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MatchingRun(Base):
    __tablename__ = "matching_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    learner_id: Mapped[int] = mapped_column(
        ForeignKey("learners.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    model_version: Mapped[str] = mapped_column(String(160), nullable=False)
    top_k: Mapped[int] = mapped_column(Integer, nullable=False)
    min_score: Mapped[float] = mapped_column(Float, nullable=False)
    same_domain: Mapped[bool] = mapped_column(Boolean, nullable=False)
    grade_band: Mapped[str | None] = mapped_column(String(8))
    need_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    creator: Mapped[User] = relationship(lazy="joined")
    recommendations: Mapped[list["GoalRecommendation"]] = relationship(
        back_populates="run",
        order_by="(GoalRecommendation.finding_id, GoalRecommendation.rank)",
        lazy="selectin",
    )

    @property
    def created_by_name(self) -> str:
        return self.creator.name


class GoalRecommendation(Base):
    __tablename__ = "goal_recommendations"
    __table_args__ = (
        UniqueConstraint("run_id", "finding_id", "goal_version_id", name="uq_goal_recommendations_run"),
        CheckConstraint(in_list("status", RecommendationStatus), name="ck_goal_recommendations_status"),
        CheckConstraint(in_list("source", RecommendationSource), name="ck_goal_recommendations_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("matching_runs.id", ondelete="CASCADE"))
    learner_id: Mapped[int] = mapped_column(
        ForeignKey("learners.id", ondelete="CASCADE"), nullable=False, index=True
    )
    finding_id: Mapped[int | None] = mapped_column(
        ForeignKey("extraction_findings.id", ondelete="SET NULL")
    )
    goal_id: Mapped[int] = mapped_column(ForeignKey("goals.id"), nullable=False)
    goal_version_id: Mapped[int] = mapped_column(ForeignKey("goal_versions.id"), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    score: Mapped[float | None] = mapped_column(Float)  # cosine similarity
    rank: Mapped[int | None] = mapped_column(Integer)  # 1 = best match for the need
    model_version: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=RecommendationStatus.SUGGESTED.value
    )
    # Learner-specific wording; the goal bank itself is never changed from here.
    edited_statement: Mapped[str | None] = mapped_column(Text)
    edited_target_value: Mapped[float | None] = mapped_column(Float)
    edited_criterion: Mapped[str | None] = mapped_column(String(300))
    reject_reason: Mapped[str | None] = mapped_column(String(300))
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    run: Mapped[MatchingRun | None] = relationship(back_populates="recommendations")
    goal: Mapped[Goal] = relationship(lazy="joined")
    goal_version: Mapped[GoalVersion] = relationship(lazy="joined")
    finding: Mapped[ExtractionFinding | None] = relationship(lazy="joined")
    decider: Mapped[User | None] = relationship(foreign_keys=[decided_by], lazy="joined")

    @property
    def decided_by_name(self) -> str | None:
        return self.decider.name if self.decider else None

    @property
    def final_statement(self) -> str:
        return self.edited_statement or self.goal_version.statement

    @property
    def final_target_value(self) -> float:
        return self.edited_target_value if self.edited_target_value is not None else self.goal_version.target_value

    @property
    def final_criterion(self) -> str | None:
        return self.edited_criterion if self.edited_criterion is not None else self.goal_version.criterion
