from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, in_list
from app.models.user import User


class AssessmentType(StrEnum):
    INFORMAL = "informal"  # from the section adviser
    FORMAL = "formal"  # psychologist report


class ProcessingStatus(StrEnum):
    """Draft → Uploaded → Processing → Processed → Needs Review → Finalized."""

    DRAFT = "draft"
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    NEEDS_REVIEW = "needs_review"
    FINALIZED = "finalized"


class Assessment(Base):
    __tablename__ = "assessments"
    __table_args__ = (
        CheckConstraint(in_list("assessment_type", AssessmentType), name="ck_assessments_type"),
        CheckConstraint(
            in_list("processing_status", ProcessingStatus), name="ck_assessments_status"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    learner_id: Mapped[int] = mapped_column(
        ForeignKey("learners.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assessment_type: Mapped[str] = mapped_column(String(16), nullable=False)
    assessment_date: Mapped[date] = mapped_column(Date, nullable=False)
    assessor: Mapped[str] = mapped_column(String(150), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    processing_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ProcessingStatus.DRAFT.value
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    creator: Mapped[User] = relationship(lazy="joined")
    document: Mapped["Document | None"] = relationship(
        back_populates="assessment", uselist=False, lazy="joined"
    )

    @property
    def created_by_name(self) -> str:
        return self.creator.name


class Document(Base):
    """Metadata for a stored file. The bytes live in object storage only."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    # Detected from the file header, not the client's Content-Type.
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    # SHA-256 hex digest, used to detect duplicate uploads.
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    assessment: Mapped[Assessment] = relationship(back_populates="document")
    uploader: Mapped[User] = relationship(lazy="joined")

    @property
    def uploaded_by_name(self) -> str:
        return self.uploader.name
