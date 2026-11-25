"""OCR jobs (a small PostgreSQL-backed queue) and per-page OCR results.

Raw OCR text and human-reviewed text are kept in separate columns: OCR only
ever writes ``raw_text``; the review screen only ever writes ``reviewed_text``.
"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, in_list
from app.models.user import User


class OcrJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class OcrPageSource(StrEnum):
    TEXT_LAYER = "text_layer"  # text taken directly from the PDF
    OCR = "ocr"  # recognised by Tesseract


class OcrPageStatus(StrEnum):
    OK = "ok"
    FAILED = "failed"


class OcrJob(Base):
    __tablename__ = "ocr_jobs"
    __table_args__ = (
        CheckConstraint(in_list("status", OcrJobStatus), name="ck_ocr_jobs_status"),
        Index("ix_ocr_jobs_status_id", "status", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=OcrJobStatus.QUEUED.value
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(500))
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OcrPage(Base):
    __tablename__ = "ocr_pages"
    __table_args__ = (
        UniqueConstraint("document_id", "page_number", name="uq_ocr_pages_document_page"),
        CheckConstraint(in_list("source", OcrPageSource), name="ck_ocr_pages_source"),
        CheckConstraint(in_list("status", OcrPageStatus), name="ck_ocr_pages_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[int | None] = mapped_column(ForeignKey("ocr_jobs.id", ondelete="SET NULL"))
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-based
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Mean word confidence 0-100; NULL for text-layer pages and failed pages.
    confidence: Mapped[float | None] = mapped_column(Float)
    error_message: Mapped[str | None] = mapped_column(String(500))
    reviewed_text: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    reviewer: Mapped[User | None] = relationship(lazy="joined")

    @property
    def effective_text(self) -> str:
        """What later stages should use: the reviewed text if any, else raw OCR."""
        return self.reviewed_text if self.reviewed_text is not None else self.raw_text

    @property
    def reviewed_by_name(self) -> str | None:
        return self.reviewer.name if self.reviewer else None
