"""Versioned extraction results (Stage 6).

Each run of an extractor, and each "edit as new draft", creates a new
``ExtractionVersion``. Drafts are editable; approved and superseded versions
are read-only. At most one version per assessment is approved at a time, and
only approved findings may be used for goal matching
(``extraction_service.approved_findings_for_learner``).
"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
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
from app.services.extraction.schema import FindingCategory, FindingDomain


class ExtractionMethod(StrEnum):
    RULE = "rule"
    AI = "ai"  # reserved for a later stage
    MANUAL = "manual"  # copied from another version to be edited


class ExtractionStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    SUPERSEDED = "superseded"


class FindingOrigin(StrEnum):
    EXTRACTED = "extracted"
    MANUAL = "manual"


class ExtractionVersion(Base):
    __tablename__ = "extraction_versions"
    __table_args__ = (
        UniqueConstraint("assessment_id", "version_number", name="uq_extraction_versions_number"),
        CheckConstraint(in_list("method", ExtractionMethod), name="ck_extraction_versions_method"),
        CheckConstraint(in_list("status", ExtractionStatus), name="ck_extraction_versions_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ExtractionStatus.DRAFT.value
    )
    based_on_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("extraction_versions.id", ondelete="SET NULL")
    )
    # SHA-256 of the assessment's page texts when the findings were extracted.
    source_text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    extractor_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    creator: Mapped[User] = relationship(foreign_keys=[created_by], lazy="joined")
    approver: Mapped[User | None] = relationship(foreign_keys=[approved_by], lazy="joined")
    findings: Mapped[list["ExtractionFinding"]] = relationship(
        back_populates="version",
        cascade="all, delete-orphan",
        order_by="(ExtractionFinding.position, ExtractionFinding.id)",
        lazy="selectin",
    )

    @property
    def created_by_name(self) -> str:
        return self.creator.name

    @property
    def approved_by_name(self) -> str | None:
        return self.approver.name if self.approver else None


class ExtractionFinding(Base):
    __tablename__ = "extraction_findings"
    __table_args__ = (
        CheckConstraint(in_list("category", FindingCategory), name="ck_extraction_findings_category"),
        CheckConstraint(
            f"domain IS NULL OR {in_list('domain', FindingDomain)}",
            name="ck_extraction_findings_domain",
        ),
        CheckConstraint(in_list("origin", FindingOrigin), name="ck_extraction_findings_origin"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("extraction_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(32))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Source reference: character offsets into that page's effective OCR text.
    source_page: Mapped[int | None] = mapped_column(Integer)
    source_start: Mapped[int | None] = mapped_column(Integer)
    source_end: Mapped[int | None] = mapped_column(Integer)
    source_quote: Mapped[str | None] = mapped_column(String(500))
    origin: Mapped[str] = mapped_column(String(16), nullable=False)
    edited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    version: Mapped[ExtractionVersion] = relationship(back_populates="findings")
