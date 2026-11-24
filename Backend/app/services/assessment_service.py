"""Assessment records and their uploaded documents.

Access always goes through ``learner_service.get_visible_learner`` so the same
learner rules apply (Teachers only see assigned learners).

Storage and database are kept consistent:
* upload: save the file first; if the DB commit then fails, delete the file.
* delete: remove the row (uncommitted), delete the file, then commit; if the
  storage delete fails, roll back so row and file both remain.
"""

import logging
import uuid
from datetime import datetime
from typing import BinaryIO

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import APIError, conflict, not_found
from app.models.assessment import Assessment, AssessmentType, Document, ProcessingStatus
from app.models.user import User
from app.schemas.assessment import AssessmentCreate
from app.services import learner_service
from app.services.file_validation import read_and_validate
from app.services.storage_service import StorageBackend, StorageError

logger = logging.getLogger(__name__)

TYPE_LABELS = {AssessmentType.INFORMAL.value: "informal", AssessmentType.FORMAL.value: "formal"}
# Statuses where the document may still be uploaded or replaced.
_OPEN_STATUSES = {ProcessingStatus.DRAFT.value, ProcessingStatus.UPLOADED.value}


def storage_unavailable() -> APIError:
    return APIError(
        502, "storage_unavailable", "The document storage service is unavailable. Please try again."
    )


# --- Assessments -------------------------------------------------------------


def create_assessment(db: Session, user: User, data: AssessmentCreate) -> Assessment:
    learner = learner_service.get_visible_learner(db, data.learner_id, user)
    assessment = Assessment(
        learner_id=learner.id,
        assessment_type=data.assessment_type.value,
        assessment_date=data.assessment_date,
        assessor=data.assessor,
        notes=data.notes,
        processing_status=ProcessingStatus.DRAFT.value,
        created_by=user.id,
    )
    db.add(assessment)
    db.commit()
    db.refresh(assessment)
    return assessment


def get_visible_assessment(db: Session, assessment_id: int, user: User) -> Assessment:
    assessment = db.get(Assessment, assessment_id)
    if assessment is None:
        raise not_found("Assessment not found.")
    try:
        learner_service.get_visible_learner(db, assessment.learner_id, user)
    except APIError as exc:
        raise not_found("Assessment not found.") from exc
    return assessment


def list_assessments(
    db: Session, user: User, learner_id: int, *, offset: int = 0, limit: int = 50
) -> tuple[list[Assessment], int]:
    learner = learner_service.get_visible_learner(db, learner_id, user)
    query = select(Assessment).where(Assessment.learner_id == learner.id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.order_by(Assessment.assessment_date.desc(), Assessment.id.desc())
        .offset(offset)
        .limit(limit)
    ).unique()
    return list(items), total


# --- Documents ---------------------------------------------------------------


def upload_document(
    db: Session,
    storage: StorageBackend,
    user: User,
    assessment: Assessment,
    stream: BinaryIO,
    filename: str | None,
) -> Assessment:
    if assessment.document is not None:
        raise conflict(
            "document_exists",
            "This assessment already has a document. Remove it before uploading another.",
        )
    if assessment.processing_status not in _OPEN_STATUSES:
        raise conflict("assessment_locked", "Documents cannot be changed at this stage.")

    file = read_and_validate(stream, filename, get_settings().max_upload_bytes)

    duplicate = db.scalar(
        select(Assessment)
        .join(Document, Document.assessment_id == Assessment.id)
        .where(Assessment.learner_id == assessment.learner_id, Document.checksum == file.checksum)
    )
    if duplicate is not None:
        raise conflict(
            "duplicate_document",
            "This file was already uploaded for this learner "
            f"({TYPE_LABELS.get(duplicate.assessment_type, duplicate.assessment_type)} assessment "
            f"dated {duplicate.assessment_date.isoformat()}).",
        )

    key = f"assessments/{uuid.uuid4()}.{file.kind.extension}"
    try:
        storage.save(key, file.data, file.kind.mime_type)
    except StorageError as exc:
        logger.error("Document upload to storage failed: %s", exc)
        raise storage_unavailable() from exc

    db.add(
        Document(
            assessment_id=assessment.id,
            original_filename=file.filename,
            mime_type=file.kind.mime_type,
            file_size=file.size,
            storage_key=key,
            checksum=file.checksum,
            uploaded_by=user.id,
        )
    )
    assessment.processing_status = ProcessingStatus.UPLOADED.value
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        # Do not leave a stored file without a database row.
        try:
            storage.delete(key)
        except StorageError:
            logger.exception("Could not remove orphaned object %s after failed commit", key)
        raise
    db.refresh(assessment)
    return assessment


def delete_document(db: Session, storage: StorageBackend, assessment: Assessment) -> Assessment:
    document = assessment.document
    if document is None:
        raise not_found("This assessment has no document.")
    if assessment.processing_status == ProcessingStatus.FINALIZED.value:
        raise conflict("assessment_finalized", "Documents of a finalized assessment cannot be removed.")

    key = document.storage_key
    db.delete(document)
    assessment.processing_status = ProcessingStatus.DRAFT.value
    db.flush()
    try:
        storage.delete(key)
    except StorageError as exc:
        # Keep the row so it still points at the (still existing) file.
        db.rollback()
        logger.error("Document delete from storage failed: %s", exc)
        raise storage_unavailable() from exc
    db.commit()
    db.refresh(assessment)
    return assessment


def document_signed_url(
    storage: StorageBackend, assessment: Assessment, *, download: bool
) -> tuple[str, int]:
    document = assessment.document
    if document is None:
        raise not_found("This assessment has no document.")
    expires_in = get_settings().signed_url_ttl_seconds
    try:
        url = storage.signed_url(
            document.storage_key,
            expires_in=expires_in,
            content_type=document.mime_type,
            filename=document.original_filename,
            download=download,
        )
    except StorageError as exc:
        logger.error("Signing document URL failed: %s", exc)
        raise storage_unavailable() from exc
    return url, expires_in


# --- Learner summary hook ----------------------------------------------------


def summary_for_learner(db: Session, learner_id: int) -> tuple[int, str | None, datetime | None]:
    count = db.scalar(select(func.count(Assessment.id)).where(Assessment.learner_id == learner_id)) or 0
    latest = db.execute(
        select(Assessment.processing_status, Assessment.updated_at)
        .where(Assessment.learner_id == learner_id)
        .order_by(Assessment.updated_at.desc(), Assessment.id.desc())
        .limit(1)
    ).first()
    return count, (latest[0] if latest else None), (latest[1] if latest else None)


learner_service.MODULE_COUNTERS["assessments"] = summary_for_learner
