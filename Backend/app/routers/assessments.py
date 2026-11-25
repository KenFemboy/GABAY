from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.permissions import (
    require_assessment_writers,
    require_document_deleters,
    require_learner_readers,
    require_status_managers,
)
from app.db.session import get_db
from app.models.assessment import Assessment
from app.models.user import User
from app.schemas.assessment import (
    AssessmentCreate,
    AssessmentList,
    AssessmentRead,
    AssessmentStatusUpdate,
    SignedUrlRead,
)
from app.core.config import get_settings
from app.models.ocr import OcrPageSource, OcrPageStatus
from app.schemas.ocr import OcrJobRead, OcrPageRead, OcrPageUpdate, OcrResultRead, OcrSummary
from app.services import assessment_service, ocr_job_service
from app.services.storage_service import StorageBackend, get_storage

router = APIRouter(prefix="/api/assessments", tags=["assessments"])


@router.get("", response_model=AssessmentList)
def list_assessments(
    learner_id: int,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(require_learner_readers),
) -> AssessmentList:
    items, total = assessment_service.list_assessments(
        db, user, learner_id, offset=offset, limit=limit
    )
    return AssessmentList(items=[AssessmentRead.model_validate(a) for a in items], total=total)


@router.post("", response_model=AssessmentRead, status_code=status.HTTP_201_CREATED)
def create_assessment(
    payload: AssessmentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_assessment_writers),
) -> Assessment:
    return assessment_service.create_assessment(db, user, payload)


@router.get("/{assessment_id}", response_model=AssessmentRead)
def get_assessment(
    assessment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_learner_readers),
) -> Assessment:
    return assessment_service.get_visible_assessment(db, assessment_id, user)


@router.patch("/{assessment_id}/status", response_model=AssessmentRead)
def change_status(
    assessment_id: int,
    payload: AssessmentStatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_status_managers),
) -> Assessment:
    assessment = assessment_service.get_visible_assessment(db, assessment_id, user)
    return assessment_service.change_status(db, assessment, payload.status)


@router.post(
    "/{assessment_id}/process", response_model=AssessmentRead, status_code=status.HTTP_202_ACCEPTED
)
def process_assessment(
    assessment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_assessment_writers),
) -> Assessment:
    """Queue OCR for the document and return immediately (the worker does the work)."""
    assessment = assessment_service.get_visible_assessment(db, assessment_id, user)
    return ocr_job_service.enqueue(db, user, assessment)


@router.get("/{assessment_id}/ocr", response_model=OcrResultRead)
def get_ocr(
    assessment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_learner_readers),
) -> OcrResultRead:
    assessment = assessment_service.get_visible_assessment(db, assessment_id, user)
    pages = ocr_job_service.list_pages(db, assessment)
    job = ocr_job_service.latest_job(db, assessment.id)
    threshold = get_settings().ocr_review_confidence
    ocr_conf = [p.confidence for p in pages if p.source == OcrPageSource.OCR and p.confidence is not None]
    summary = OcrSummary(
        page_count=len(pages),
        failed_pages=sum(1 for p in pages if p.status == OcrPageStatus.FAILED),
        low_confidence_pages=sum(1 for c in ocr_conf if c < threshold),
        reviewed_pages=sum(1 for p in pages if p.reviewed_text is not None),
        mean_confidence=round(sum(ocr_conf) / len(ocr_conf), 1) if ocr_conf else None,
        review_confidence=threshold,
    )
    return OcrResultRead(
        job=OcrJobRead.model_validate(job) if job else None,
        pages=[OcrPageRead.model_validate(p) for p in pages],
        summary=summary,
    )


@router.put("/{assessment_id}/ocr/pages/{page_number}", response_model=OcrPageRead)
def update_ocr_page(
    assessment_id: int,
    page_number: int,
    payload: OcrPageUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_assessment_writers),
):
    assessment = assessment_service.get_visible_assessment(db, assessment_id, user)
    return ocr_job_service.update_reviewed_text(db, user, assessment, page_number, payload.reviewed_text)


@router.post("/{assessment_id}/document", response_model=AssessmentRead)
def upload_document(
    assessment_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
    user: User = Depends(require_assessment_writers),
) -> Assessment:
    assessment = assessment_service.get_visible_assessment(db, assessment_id, user)
    return assessment_service.upload_document(
        db, storage, user, assessment, file.file, file.filename
    )


@router.get("/{assessment_id}/document", response_model=SignedUrlRead)
def get_document_url(
    assessment_id: int,
    download: bool = False,
    db: Session = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
    user: User = Depends(require_learner_readers),
) -> SignedUrlRead:
    """Short-lived signed URL for preview (inline) or download (attachment)."""
    assessment = assessment_service.get_visible_assessment(db, assessment_id, user)
    url, expires_in = assessment_service.document_signed_url(storage, assessment, download=download)
    return SignedUrlRead(url=url, expires_in=expires_in)


@router.delete("/{assessment_id}/document", response_model=AssessmentRead)
def delete_document(
    assessment_id: int,
    db: Session = Depends(get_db),
    storage: StorageBackend = Depends(get_storage),
    user: User = Depends(require_document_deleters),
) -> Assessment:
    assessment = assessment_service.get_visible_assessment(db, assessment_id, user)
    return assessment_service.delete_document(db, storage, assessment)
