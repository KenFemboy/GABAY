"""Extraction versions and findings: run, edit, approve (Stage 6).

Workflow: the assessment's OCR text is reviewed and the assessment Finalized
-> run extraction (creates a draft version) -> edit the draft -> the SNED
Coordinator approves it. Approving supersedes the previously approved version.

Goal matching (a later stage) must read findings ONLY through
``approved_findings_for_learner``; drafts and superseded versions are never
exposed there.
"""

import hashlib
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import APIError, conflict, not_found
from app.models.assessment import Assessment, ProcessingStatus
from app.models.extraction import (
    ExtractionFinding,
    ExtractionMethod,
    ExtractionStatus,
    ExtractionVersion,
    FindingOrigin,
)
from app.models.ocr import OcrPageStatus
from app.models.user import User
from app.services import assessment_service, ocr_job_service
from app.services.extraction.registry import get_extractor
from app.services.extraction.schema import FindingCategory, FindingDomain, PageText

DRAFT = ExtractionStatus.DRAFT.value
APPROVED = ExtractionStatus.APPROVED.value
SUPERSEDED = ExtractionStatus.SUPERSEDED.value


def _now() -> datetime:
    return datetime.now(UTC)


# --- Source text -------------------------------------------------------------


def page_texts(db: Session, assessment: Assessment) -> list[PageText]:
    """The reviewed text of every readable page, in page order."""
    return [
        PageText(page_number=p.page_number, text=p.effective_text)
        for p in ocr_job_service.list_pages(db, assessment)
        if p.status == OcrPageStatus.OK.value
    ]


def text_hash(pages: list[PageText]) -> str:
    digest = hashlib.sha256()
    for page in pages:
        digest.update(f"{page.page_number}\x00{page.text}\x01".encode())
    return digest.hexdigest()


def current_text_hash(db: Session, assessment: Assessment) -> str:
    return text_hash(page_texts(db, assessment))


def is_stale(db: Session, version: ExtractionVersion, assessment: Assessment | None = None) -> bool:
    assessment = assessment or db.get(Assessment, version.assessment_id)
    return version.source_text_hash != current_text_hash(db, assessment)


# --- Lookups -----------------------------------------------------------------


def get_visible_version(db: Session, version_id: int, user: User) -> tuple[ExtractionVersion, Assessment]:
    version = db.get(ExtractionVersion, version_id)
    if version is None:
        raise not_found("Extraction not found.")
    try:
        assessment = assessment_service.get_visible_assessment(db, version.assessment_id, user)
    except APIError as exc:
        raise not_found("Extraction not found.") from exc
    return version, assessment


def list_versions(db: Session, assessment: Assessment) -> list[ExtractionVersion]:
    return list(
        db.scalars(
            select(ExtractionVersion)
            .where(ExtractionVersion.assessment_id == assessment.id)
            .order_by(ExtractionVersion.version_number.desc())
        ).unique()
    )


def _draft_for(db: Session, assessment_id: int) -> ExtractionVersion | None:
    return db.scalar(
        select(ExtractionVersion).where(
            ExtractionVersion.assessment_id == assessment_id, ExtractionVersion.status == DRAFT
        )
    )


def _next_number(db: Session, assessment_id: int) -> int:
    current = db.scalar(
        select(func.max(ExtractionVersion.version_number)).where(
            ExtractionVersion.assessment_id == assessment_id
        )
    )
    return (current or 0) + 1


def _require_finalized(assessment: Assessment) -> None:
    if assessment.processing_status != ProcessingStatus.FINALIZED.value:
        raise conflict(
            "assessment_not_finalized",
            "Review the OCR text and finalize the assessment before extracting findings.",
        )


def _require_draft(version: ExtractionVersion) -> None:
    if version.status != DRAFT:
        raise conflict(
            "version_not_draft",
            "Approved versions cannot be changed. Use 'Edit as new draft' instead.",
        )


def _require_no_other_draft(db: Session, assessment_id: int) -> None:
    if _draft_for(db, assessment_id) is not None:
        raise conflict(
            "draft_exists",
            "This assessment already has a draft. Approve or discard it first.",
        )


# --- Running extraction ------------------------------------------------------


def run_extraction(
    db: Session, user: User, assessment: Assessment, method: str = ExtractionMethod.RULE.value
) -> ExtractionVersion:
    _require_finalized(assessment)
    _require_no_other_draft(db, assessment.id)
    pages = page_texts(db, assessment)
    if not pages:
        raise conflict("no_text", "There is no OCR text to extract findings from.")

    extractor = get_extractor(method)
    result = extractor.extract(pages)

    version = ExtractionVersion(
        assessment_id=assessment.id,
        version_number=_next_number(db, assessment.id),
        method=extractor.method,
        status=DRAFT,
        source_text_hash=text_hash(pages),
        extractor_version=result.extractor,
        created_by=user.id,
    )
    for position, draft in enumerate(result.findings):
        source = draft.source
        version.findings.append(
            ExtractionFinding(
                category=draft.category.value,
                domain=draft.domain.value if draft.domain else None,
                text=draft.text,
                position=position,
                source_page=source.page if source else None,
                source_start=source.start if source else None,
                source_end=source.end if source else None,
                source_quote=source.quote if source else None,
                origin=FindingOrigin.EXTRACTED.value,
                edited=False,
            )
        )
    db.add(version)
    db.commit()
    db.refresh(version)
    return version


def copy_to_draft(db: Session, user: User, version: ExtractionVersion, assessment: Assessment) -> ExtractionVersion:
    """'Edit as new draft': copy any version into a new editable draft."""
    _require_finalized(assessment)
    _require_no_other_draft(db, assessment.id)
    copy = ExtractionVersion(
        assessment_id=assessment.id,
        version_number=_next_number(db, assessment.id),
        method=ExtractionMethod.MANUAL.value,
        status=DRAFT,
        based_on_version_id=version.id,
        source_text_hash=version.source_text_hash,
        extractor_version=version.extractor_version,
        created_by=user.id,
    )
    for f in version.findings:
        copy.findings.append(
            ExtractionFinding(
                category=f.category,
                domain=f.domain,
                text=f.text,
                position=f.position,
                source_page=f.source_page,
                source_start=f.source_start,
                source_end=f.source_end,
                source_quote=f.source_quote,
                origin=f.origin,
                edited=f.edited,
            )
        )
    db.add(copy)
    db.commit()
    db.refresh(copy)
    return copy


# --- Editing a draft ---------------------------------------------------------


def _get_finding(version: ExtractionVersion, finding_id: int) -> ExtractionFinding:
    for finding in version.findings:
        if finding.id == finding_id:
            return finding
    raise not_found("Finding not found.")


def add_finding(
    db: Session,
    version: ExtractionVersion,
    category: FindingCategory,
    text: str,
    domain: FindingDomain | None,
) -> ExtractionFinding:
    _require_draft(version)
    position = max((f.position for f in version.findings), default=-1) + 1
    finding = ExtractionFinding(
        category=category.value,
        domain=domain.value if domain else None,
        text=text,
        position=position,
        origin=FindingOrigin.MANUAL.value,
        edited=False,
    )
    version.findings.append(finding)
    db.commit()
    db.refresh(finding)
    return finding


def update_finding(db: Session, version: ExtractionVersion, finding_id: int, changes: dict) -> ExtractionFinding:
    _require_draft(version)
    finding = _get_finding(version, finding_id)
    changed = False
    if "text" in changes and changes["text"] != finding.text:
        finding.text = changes["text"]
        changed = True
    if "category" in changes and changes["category"].value != finding.category:
        finding.category = changes["category"].value
        changed = True
    if "domain" in changes:
        new_domain = changes["domain"].value if changes["domain"] else None
        if new_domain != finding.domain:
            finding.domain = new_domain
            changed = True
    if changed and finding.origin == FindingOrigin.EXTRACTED.value:
        finding.edited = True
    db.commit()
    db.refresh(finding)
    return finding


def delete_finding(db: Session, version: ExtractionVersion, finding_id: int) -> None:
    _require_draft(version)
    finding = _get_finding(version, finding_id)
    version.findings.remove(finding)
    db.commit()


def reorder(db: Session, version: ExtractionVersion, finding_ids: list[int]) -> ExtractionVersion:
    _require_draft(version)
    by_id = {f.id: f for f in version.findings}
    if sorted(finding_ids) != sorted(by_id):
        raise APIError(422, "invalid_order", "The order must list every finding of this version once.")
    for position, finding_id in enumerate(finding_ids):
        by_id[finding_id].position = position
    db.commit()
    db.expire(version, ["findings"])
    return version


def discard_draft(db: Session, version: ExtractionVersion) -> None:
    _require_draft(version)
    db.delete(version)
    db.commit()


# --- Approval ----------------------------------------------------------------


def approve(db: Session, user: User, version: ExtractionVersion, assessment: Assessment) -> ExtractionVersion:
    _require_draft(version)
    _require_finalized(assessment)
    if is_stale(db, version, assessment):
        raise conflict(
            "source_changed",
            "The OCR text changed after these findings were extracted. Run extraction again.",
        )
    if not version.findings:
        raise conflict("no_findings", "A version with no findings cannot be approved.")
    previous = db.scalars(
        select(ExtractionVersion).where(
            ExtractionVersion.assessment_id == assessment.id,
            ExtractionVersion.status == APPROVED,
        )
    ).all()
    for old in previous:
        old.status = SUPERSEDED
    version.status = APPROVED
    version.approved_by = user.id
    version.approved_at = _now()
    db.commit()
    db.refresh(version)
    return version


# --- Goal-matching gate ------------------------------------------------------


def approved_versions_for_learner(db: Session, learner_id: int) -> list[ExtractionVersion]:
    return list(
        db.scalars(
            select(ExtractionVersion)
            .join(Assessment, Assessment.id == ExtractionVersion.assessment_id)
            .where(Assessment.learner_id == learner_id, ExtractionVersion.status == APPROVED)
            .order_by(Assessment.assessment_date.desc(), ExtractionVersion.id.desc())
        ).unique()
    )


def approved_findings_for_learner(db: Session, learner_id: int) -> list[ExtractionFinding]:
    """The ONLY source of findings for goal matching: approved versions only."""
    return [f for v in approved_versions_for_learner(db, learner_id) for f in v.findings]


def approved_findings_count(db: Session, assessment_id: int) -> int:
    return (
        db.scalar(
            select(func.count(ExtractionFinding.id))
            .join(ExtractionVersion, ExtractionVersion.id == ExtractionFinding.version_id)
            .where(
                ExtractionVersion.assessment_id == assessment_id,
                ExtractionVersion.status == APPROVED,
            )
        )
        or 0
    )
