"""Assessment processing-status flow: the single source of allowed transitions.

Draft → Uploaded → Processing → Processed → Needs Review → Finalized.

* System transitions happen as side effects of events: document uploaded or
  removed, OCR queued (``ocr_job_service.enqueue``), OCR finished or failed
  (the OCR worker).
* Manual transitions are what a user may request via
  ``PATCH /api/assessments/{id}/status``.

``transition`` flushes but never commits, so callers keep control of the
database/storage consistency logic around it.
"""

from sqlalchemy import update
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import set_committed_value

from app.core.errors import conflict
from app.models.assessment import Assessment, ProcessingStatus

S = ProcessingStatus

LABELS = {
    S.DRAFT: "Draft",
    S.UPLOADED: "Uploaded",
    S.PROCESSING: "Processing",
    S.PROCESSED: "Processed",
    S.NEEDS_REVIEW: "Needs Review",
    S.FINALIZED: "Finalized",
}

SYSTEM_TRANSITIONS: frozenset[tuple[ProcessingStatus, ProcessingStatus]] = frozenset(
    {
        (S.DRAFT, S.UPLOADED),  # document uploaded
        (S.UPLOADED, S.DRAFT),  # document removed
        (S.PROCESSED, S.DRAFT),
        (S.NEEDS_REVIEW, S.DRAFT),
        (S.UPLOADED, S.PROCESSING),  # OCR queued
        (S.PROCESSED, S.PROCESSING),  # reprocess
        (S.NEEDS_REVIEW, S.PROCESSING),
        (S.PROCESSING, S.PROCESSED),  # OCR finished, all pages good
        (S.PROCESSING, S.NEEDS_REVIEW),  # OCR finished, some pages failed or low confidence
        (S.PROCESSING, S.UPLOADED),  # OCR failed completely; may be retried
    }
)

# Ordered so the UI can show buttons in a sensible order.
MANUAL_TRANSITIONS: dict[ProcessingStatus, tuple[ProcessingStatus, ...]] = {
    S.PROCESSED: (S.NEEDS_REVIEW, S.FINALIZED),
    S.NEEDS_REVIEW: (S.FINALIZED,),
    S.FINALIZED: (S.NEEDS_REVIEW,),  # reopen
}


def next_manual_statuses(current: str | ProcessingStatus) -> list[ProcessingStatus]:
    return list(MANUAL_TRANSITIONS.get(ProcessingStatus(current), ()))


def is_allowed(current: ProcessingStatus, target: ProcessingStatus, *, manual: bool) -> bool:
    if manual:
        return target in MANUAL_TRANSITIONS.get(current, ())
    return (current, target) in SYSTEM_TRANSITIONS


def transition(
    db: Session, assessment: Assessment, target: ProcessingStatus, *, manual: bool
) -> None:
    current = ProcessingStatus(assessment.processing_status)
    target = ProcessingStatus(target)
    if not is_allowed(current, target, manual=manual):
        raise conflict(
            "invalid_status_transition",
            f"An assessment cannot move from {LABELS[current]} to {LABELS[target]}.",
        )

    # Guarded update: fails if someone else changed the status since we read it.
    result = db.execute(
        update(Assessment)
        .where(Assessment.id == assessment.id, Assessment.processing_status == current.value)
        .values(processing_status=target.value)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise conflict(
            "status_changed",
            "This assessment was changed by someone else. Reload and try again.",
        )
    # Keep the in-memory object in step without marking it dirty.
    set_committed_value(assessment, "processing_status", target.value)
