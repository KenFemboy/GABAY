"""Year-end evaluation (Stage 12).

A narrative report per learner and school year covering progress on each goal
of the active IEP. It is drafted either by AI (OpenAI, from a de-identified
evidence package) or manually from a prefilled skeleton, then edited and
finalized by staff. AI drafts keep full provenance: model, prompt version,
evidence IDs, the exact de-identified package sent and the raw response.
"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, in_list
from app.models.user import User


class EvaluationStatus(StrEnum):
    DRAFT = "draft"
    FINALIZED = "finalized"


class EvaluationSource(StrEnum):
    AI = "ai"
    MANUAL = "manual"


class GoalRating(StrEnum):
    MET = "met"
    PROGRESSING = "progressing"
    LIMITED_PROGRESS = "limited_progress"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class Evaluation(Base):
    __tablename__ = "evaluations"
    __table_args__ = (
        CheckConstraint(in_list("status", EvaluationStatus), name="ck_evaluations_status"),
        CheckConstraint(in_list("source", EvaluationSource), name="ck_evaluations_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    learner_id: Mapped[int] = mapped_column(
        ForeignKey("learners.id", ondelete="CASCADE"), nullable=False, index=True
    )
    iep_id: Mapped[int] = mapped_column(ForeignKey("ieps.id"), nullable=False)
    school_year: Mapped[str] = mapped_column(String(9), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=EvaluationStatus.DRAFT.value)
    source: Mapped[str] = mapped_column(String(16), nullable=False)

    # AI provenance (null for manual drafts).
    model: Mapped[str | None] = mapped_column(String(120))
    prompt_version: Mapped[str | None] = mapped_column(String(40))
    evidence_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence_hash: Mapped[str | None] = mapped_column(String(64))
    # The de-identified evidence package exactly as built (and, for AI drafts, as sent).
    evidence_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    raw_response: Mapped[str | None] = mapped_column(Text)  # de-identified model output
    validation_warnings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    generation_error: Mapped[str | None] = mapped_column(String(500))

    # {summary, goals: [{iep_goal_id, rating, narrative, evidence_ids}], strengths: [...], recommendations: [...]}
    content: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

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

    @property
    def created_by_name(self) -> str:
        return self.creator.name

    @property
    def finalized_by_name(self) -> str | None:
        return self.finalizer.name if self.finalizer else None

    @property
    def read_only(self) -> bool:
        return self.status == EvaluationStatus.FINALIZED.value
