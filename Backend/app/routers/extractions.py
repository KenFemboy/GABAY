"""Extraction versions, findings and approval (Stage 6)."""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.permissions import (
    require_assessment_writers,
    require_extraction_approvers,
    require_learner_readers,
)
from app.db.session import get_db
from app.models.extraction import ExtractionVersion
from app.models.user import User
from app.schemas.extraction import (
    FindingCreate,
    FindingOrder,
    FindingRead,
    FindingUpdate,
    LearnerFinding,
    LearnerFindingList,
    VersionList,
    VersionRead,
    VersionSummary,
)
from app.services import assessment_service, extraction_service, learner_service

router = APIRouter(prefix="/api", tags=["extractions"])


def _summary(db: Session, version: ExtractionVersion, current_hash: str) -> dict:
    return {
        **VersionSummary.model_validate(version).model_dump(),
        "finding_count": len(version.findings),
        "is_stale": version.source_text_hash != current_hash,
    }


def _read(db: Session, version: ExtractionVersion, assessment) -> VersionRead:
    current_hash = extraction_service.current_text_hash(db, assessment)
    return VersionRead(
        **_summary(db, version, current_hash),
        findings=[FindingRead.model_validate(f) for f in version.findings],
    )


@router.post(
    "/assessments/{assessment_id}/extractions",
    response_model=VersionRead,
    status_code=status.HTTP_201_CREATED,
)
def run_extraction(
    assessment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_assessment_writers),
) -> VersionRead:
    assessment = assessment_service.get_visible_assessment(db, assessment_id, user)
    version = extraction_service.run_extraction(db, user, assessment)
    return _read(db, version, assessment)


@router.get("/assessments/{assessment_id}/extractions", response_model=VersionList)
def list_extractions(
    assessment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_learner_readers),
) -> VersionList:
    assessment = assessment_service.get_visible_assessment(db, assessment_id, user)
    current_hash = extraction_service.current_text_hash(db, assessment)
    versions = extraction_service.list_versions(db, assessment)
    return VersionList(items=[VersionSummary(**_summary(db, v, current_hash)) for v in versions])


@router.get("/extractions/{version_id}", response_model=VersionRead)
def get_extraction(
    version_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_learner_readers),
) -> VersionRead:
    version, assessment = extraction_service.get_visible_version(db, version_id, user)
    return _read(db, version, assessment)


@router.post(
    "/extractions/{version_id}/findings",
    response_model=FindingRead,
    status_code=status.HTTP_201_CREATED,
)
def add_finding(
    version_id: int,
    payload: FindingCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_assessment_writers),
):
    version, _ = extraction_service.get_visible_version(db, version_id, user)
    return extraction_service.add_finding(db, version, payload.category, payload.text, payload.domain)


@router.patch("/extractions/{version_id}/findings/{finding_id}", response_model=FindingRead)
def update_finding(
    version_id: int,
    finding_id: int,
    payload: FindingUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_assessment_writers),
):
    version, _ = extraction_service.get_visible_version(db, version_id, user)
    # Only fields that were sent; "domain": null clears the domain, while a null
    # category or text is ignored (both are required on a finding).
    changes = {
        k: v
        for k, v in payload.model_dump(exclude_unset=True).items()
        if v is not None or k == "domain"
    }
    return extraction_service.update_finding(db, version, finding_id, changes)


@router.delete(
    "/extractions/{version_id}/findings/{finding_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_finding(
    version_id: int,
    finding_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_assessment_writers),
) -> Response:
    version, _ = extraction_service.get_visible_version(db, version_id, user)
    extraction_service.delete_finding(db, version, finding_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/extractions/{version_id}/order", response_model=VersionRead)
def reorder_findings(
    version_id: int,
    payload: FindingOrder,
    db: Session = Depends(get_db),
    user: User = Depends(require_assessment_writers),
) -> VersionRead:
    version, assessment = extraction_service.get_visible_version(db, version_id, user)
    version = extraction_service.reorder(db, version, payload.finding_ids)
    return _read(db, version, assessment)


@router.post(
    "/extractions/{version_id}/copy", response_model=VersionRead, status_code=status.HTTP_201_CREATED
)
def copy_extraction(
    version_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_assessment_writers),
) -> VersionRead:
    version, assessment = extraction_service.get_visible_version(db, version_id, user)
    copy = extraction_service.copy_to_draft(db, user, version, assessment)
    return _read(db, copy, assessment)


@router.post("/extractions/{version_id}/approve", response_model=VersionRead)
def approve_extraction(
    version_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_extraction_approvers),
) -> VersionRead:
    version, assessment = extraction_service.get_visible_version(db, version_id, user)
    version = extraction_service.approve(db, user, version, assessment)
    return _read(db, version, assessment)


@router.delete("/extractions/{version_id}", status_code=status.HTTP_204_NO_CONTENT)
def discard_extraction(
    version_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_assessment_writers),
) -> Response:
    version, _ = extraction_service.get_visible_version(db, version_id, user)
    extraction_service.discard_draft(db, version)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/learners/{learner_id}/findings", response_model=LearnerFindingList)
def learner_findings(
    learner_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_learner_readers),
) -> LearnerFindingList:
    """Approved findings only - the input for goal matching."""
    learner = learner_service.get_visible_learner(db, learner_id, user)
    items: list[LearnerFinding] = []
    hashes: dict[int, str] = {}
    for version in extraction_service.approved_versions_for_learner(db, learner.id):
        if version.assessment_id not in hashes:
            assessment = assessment_service.get_visible_assessment(db, version.assessment_id, user)
            hashes[version.assessment_id] = extraction_service.current_text_hash(db, assessment)
        stale = version.source_text_hash != hashes[version.assessment_id]
        for finding in version.findings:
            items.append(
                LearnerFinding(
                    **FindingRead.model_validate(finding).model_dump(),
                    assessment_id=version.assessment_id,
                    version_id=version.id,
                    version_number=version.version_number,
                    stale=stale,
                )
            )
    return LearnerFindingList(items=items)
