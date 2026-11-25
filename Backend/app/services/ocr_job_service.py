"""OCR job queue stored in PostgreSQL, plus OCR results and review edits.

The API only enqueues (``enqueue``) and returns. The separate worker process
(``app.workers.ocr_worker``) claims jobs, runs ``ocr_service.extract_pages``
and records the outcome with ``complete`` or ``fail``.

Assessment status moves go through ``assessment_status.transition`` so the
status flow stays in one place.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import APIError, conflict, not_found
from app.models.assessment import Assessment, ProcessingStatus
from app.models.ocr import OcrJob, OcrJobStatus, OcrPage, OcrPageSource, OcrPageStatus
from app.models.user import User
from app.services.assessment_status import transition
from app.services.ocr_service import PageResult

logger = logging.getLogger(__name__)

S = ProcessingStatus
PROCESSABLE = {S.UPLOADED.value, S.PROCESSED.value, S.NEEDS_REVIEW.value}
EDITABLE = {S.PROCESSED.value, S.NEEDS_REVIEW.value}
MAX_REVIEWED_CHARS = 100_000


def _now() -> datetime:
    return datetime.now(UTC)


# --- API side ----------------------------------------------------------------


def enqueue(db: Session, user: User, assessment: Assessment) -> Assessment:
    if assessment.document is None:
        raise conflict("no_document", "Upload a document before processing.")
    if assessment.processing_status not in PROCESSABLE:
        raise conflict(
            "assessment_not_processable",
            "This assessment cannot be processed in its current status.",
        )
    try:
        # Guarded: a concurrent second request fails here with 409.
        transition(db, assessment, S.PROCESSING, manual=False)
        db.add(
            OcrJob(
                assessment_id=assessment.id,
                document_id=assessment.document.id,
                status=OcrJobStatus.QUEUED.value,
                requested_by=user.id,
            )
        )
        db.commit()
    except APIError:
        db.rollback()
        raise
    db.refresh(assessment)
    return assessment


def latest_job(db: Session, assessment_id: int) -> OcrJob | None:
    return db.scalar(
        select(OcrJob).where(OcrJob.assessment_id == assessment_id).order_by(OcrJob.id.desc()).limit(1)
    )


def latest_error(db: Session, assessment_id: int) -> str | None:
    job = latest_job(db, assessment_id)
    if job is not None and job.status == OcrJobStatus.FAILED.value:
        return job.error_message
    return None


def list_pages(db: Session, assessment: Assessment) -> list[OcrPage]:
    if assessment.document is None:
        return []
    return list(
        db.scalars(
            select(OcrPage)
            .where(OcrPage.document_id == assessment.document.id)
            .order_by(OcrPage.page_number)
        ).unique()
    )


def update_reviewed_text(
    db: Session, user: User, assessment: Assessment, page_number: int, text: str | None
) -> OcrPage:
    if assessment.processing_status not in EDITABLE:
        raise conflict(
            "assessment_not_editable", "OCR text can only be edited while the assessment is in review."
        )
    page = None
    if assessment.document is not None:
        page = db.scalar(
            select(OcrPage).where(
                OcrPage.document_id == assessment.document.id, OcrPage.page_number == page_number
            )
        )
    if page is None:
        raise not_found("Page not found.")
    if text is None:
        page.reviewed_text = None
        page.reviewed_by = None
        page.reviewed_at = None
    else:
        page.reviewed_text = text
        page.reviewed_by = user.id
        page.reviewed_at = _now()
    db.commit()
    db.refresh(page)
    return page


# --- Worker side -------------------------------------------------------------


def claim_next(db: Session) -> OcrJob | None:
    """Take the oldest queued job. SKIP LOCKED lets several workers run safely."""
    job = db.scalar(
        select(OcrJob)
        .where(OcrJob.status == OcrJobStatus.QUEUED.value)
        .order_by(OcrJob.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job is None:
        db.rollback()
        return None
    job.status = OcrJobStatus.RUNNING.value
    job.started_at = _now()
    job.attempts += 1
    db.commit()
    return job


def needs_review(pages: list[PageResult], settings: Settings) -> bool:
    for page in pages:
        if page.status != OcrPageStatus.OK:
            return True
        if page.source == OcrPageSource.OCR and (
            page.confidence is None or page.confidence < settings.ocr_review_confidence
        ):
            return True
    return False


def complete(
    db: Session, job: OcrJob, pages: list[PageResult], settings: Settings | None = None
) -> None:
    settings = settings or get_settings()
    if not pages or all(p.status != OcrPageStatus.OK for p in pages):
        fail(db, job, "all_pages_failed", "No page of the document could be read.")
        return
    assessment = db.get(Assessment, job.assessment_id)
    if assessment is None or assessment.processing_status != S.PROCESSING.value:
        # Assessment changed or vanished while we worked; drop the result.
        job.status = OcrJobStatus.FAILED.value
        job.error_code = "assessment_changed"
        job.error_message = "The assessment changed while it was being processed."
        job.finished_at = _now()
        db.commit()
        return

    db.execute(delete(OcrPage).where(OcrPage.document_id == job.document_id))
    for page in sorted(pages, key=lambda p: p.page_number):
        db.add(
            OcrPage(
                document_id=job.document_id,
                job_id=job.id,
                page_number=page.page_number,
                source=page.source.value,
                status=page.status.value,
                raw_text=page.text,
                confidence=page.confidence,
                error_message=page.error,
            )
        )
    target = S.NEEDS_REVIEW if needs_review(pages, settings) else S.PROCESSED
    transition(db, assessment, target, manual=False)
    job.status = OcrJobStatus.SUCCEEDED.value
    job.error_code = None
    job.error_message = None
    job.finished_at = _now()
    db.commit()


def fail(db: Session, job: OcrJob, code: str, message: str) -> None:
    db.rollback()
    job = db.get(OcrJob, job.id)
    job.status = OcrJobStatus.FAILED.value
    job.error_code = code
    job.error_message = message[:500]
    job.finished_at = _now()
    assessment = db.get(Assessment, job.assessment_id)
    if assessment is not None and assessment.processing_status == S.PROCESSING.value:
        transition(db, assessment, S.UPLOADED, manual=False)
    db.commit()


def recover_stale(db: Session, settings: Settings | None = None) -> int:
    """Requeue (or fail) jobs left running by a crashed or killed worker."""
    settings = settings or get_settings()
    cutoff = _now() - timedelta(minutes=settings.ocr_job_timeout_minutes)
    stale = list(
        db.scalars(
            select(OcrJob).where(
                OcrJob.status == OcrJobStatus.RUNNING.value, OcrJob.started_at < cutoff
            )
        )
    )
    for job in stale:
        if job.attempts < settings.ocr_max_attempts:
            logger.warning("Requeueing stale OCR job %s", job.id)
            job.status = OcrJobStatus.QUEUED.value
            job.started_at = None
            db.commit()
        else:
            logger.warning("Failing stale OCR job %s after %s attempts", job.id, job.attempts)
            fail(db, job, "job_timeout", "Processing did not finish. Try processing again.")
    return len(stale)
