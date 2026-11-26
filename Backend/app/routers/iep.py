"""IEP builder API (Stage 9)."""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.permissions import require_assessment_writers, require_iep_finalizers, require_learner_readers
from app.db.session import get_db
from app.models.iep import Iep
from app.models.learner import Learner
from app.models.user import User
from app.schemas.iep import (
    AmendBody,
    IepFindingCreate,
    IepFindingRead,
    IepFindingUpdate,
    IepGoalCreate,
    IepGoalFields,
    IepGoalRead,
    IepList,
    IepRead,
    IepSummary,
    IepUpdate,
    ImportResult,
    IssueRead,
    OrderBody,
)
from app.services import iep_document, iep_service, learner_service

router = APIRouter(prefix="/api", tags=["iep"])

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _visible(db: Session, iep_id: int, user: User) -> tuple[Iep, Learner]:
    iep = iep_service.get_iep(db, iep_id)
    learner = learner_service.get_visible_learner(db, iep.learner_id, user)
    return iep, learner


def _summary(iep: Iep) -> IepSummary:
    return IepSummary.model_validate(iep).model_copy(update={"goal_count": len(iep.goals)})


def _read(iep: Iep) -> IepRead:
    data = IepSummary.model_validate(iep).model_dump()
    data["goal_count"] = len(iep.goals)
    return IepRead(
        **data,
        annual_review_date=iep.annual_review_date,
        accommodations=iep.accommodations,
        services=iep.services,
        notes=iep.notes,
        team_members=list(iep.team_members or []),
        findings=[IepFindingRead.model_validate(f) for f in iep.findings],
        goals=[IepGoalRead.model_validate(g) for g in iep.goals],
        validation=[IssueRead(**i) for i in iep_service.issues_payload(iep_service.validate(iep))],
    )


def _changes(payload) -> dict:
    data = payload.model_dump(exclude_unset=True)
    if "team_members" in data and data["team_members"] is not None:
        data["team_members"] = [dict(m) for m in data["team_members"]]
    if "review_dates" in data:
        data["review_dates"] = [d.isoformat() for d in (data["review_dates"] or [])]
    for key in ("domain", "measurement_method", "target_unit", "category"):
        if key in data and data[key] is not None and hasattr(data[key], "value"):
            data[key] = data[key].value
    return data


# --- IEPs ------------------------------------------------------------------------------


@router.get("/learners/{learner_id}/ieps", response_model=IepList)
def list_ieps(learner_id: int, db: Session = Depends(get_db), user: User = Depends(require_learner_readers)):
    learner = learner_service.get_visible_learner(db, learner_id, user)
    return IepList(items=[_summary(i) for i in iep_service.history(db, learner.id)])


@router.post("/learners/{learner_id}/ieps", response_model=ImportResult, status_code=status.HTTP_201_CREATED)
def create_iep(learner_id: int, db: Session = Depends(get_db), user: User = Depends(require_assessment_writers)):
    learner = learner_service.get_visible_learner(db, learner_id, user)
    iep, counts = iep_service.create_draft(db, user, learner)
    return ImportResult(**counts, iep=_read(iep))


@router.get("/ieps/{iep_id}", response_model=IepRead)
def get_iep(iep_id: int, db: Session = Depends(get_db), user: User = Depends(require_learner_readers)):
    return _read(_visible(db, iep_id, user)[0])


@router.patch("/ieps/{iep_id}", response_model=IepRead)
def update_iep(iep_id: int, payload: IepUpdate, db: Session = Depends(get_db), user: User = Depends(require_assessment_writers)):
    iep, _ = _visible(db, iep_id, user)
    return _read(iep_service.update_iep(db, iep, _changes(payload)))


@router.post("/ieps/{iep_id}/import", response_model=ImportResult)
def reimport(iep_id: int, db: Session = Depends(get_db), user: User = Depends(require_assessment_writers)):
    iep, _ = _visible(db, iep_id, user)
    counts = iep_service.import_sources(db, iep)
    return ImportResult(**counts, iep=_read(iep))


@router.delete("/ieps/{iep_id}", status_code=status.HTTP_204_NO_CONTENT)
def discard(iep_id: int, db: Session = Depends(get_db), user: User = Depends(require_assessment_writers)):
    iep, _ = _visible(db, iep_id, user)
    iep_service.discard_draft(db, iep)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/ieps/{iep_id}/validation", response_model=list[IssueRead])
def validation(iep_id: int, db: Session = Depends(get_db), user: User = Depends(require_learner_readers)):
    iep, _ = _visible(db, iep_id, user)
    return [IssueRead(**i) for i in iep_service.issues_payload(iep_service.validate(iep))]


@router.post("/ieps/{iep_id}/finalize", response_model=IepRead)
def finalize(iep_id: int, db: Session = Depends(get_db), user: User = Depends(require_iep_finalizers)):
    iep, _ = _visible(db, iep_id, user)
    return _read(iep_service.finalize(db, user, iep))


@router.post("/ieps/{iep_id}/amend", response_model=IepRead, status_code=status.HTTP_201_CREATED)
def amend(iep_id: int, payload: AmendBody, db: Session = Depends(get_db), user: User = Depends(require_iep_finalizers)):
    iep, _ = _visible(db, iep_id, user)
    return _read(iep_service.amend(db, user, iep, payload.reason))


@router.get("/ieps/{iep_id}/document")
def document(iep_id: int, db: Session = Depends(get_db), user: User = Depends(require_learner_readers)) -> Response:
    iep, learner = _visible(db, iep_id, user)
    content = iep_document.build_iep_docx(iep, learner)
    return Response(
        content=content,
        media_type=DOCX_MIME,
        headers={
            "Content-Disposition": f'attachment; filename="{iep_document.filename(iep, learner)}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


# --- Findings ------------------------------------------------------------------------------


@router.post("/ieps/{iep_id}/findings", response_model=IepFindingRead, status_code=status.HTTP_201_CREATED)
def add_finding(iep_id: int, payload: IepFindingCreate, db: Session = Depends(get_db), user: User = Depends(require_assessment_writers)):
    iep, _ = _visible(db, iep_id, user)
    return iep_service.add_finding(db, iep, _changes(payload))


@router.patch("/ieps/{iep_id}/findings/{finding_id}", response_model=IepFindingRead)
def update_finding(iep_id: int, finding_id: int, payload: IepFindingUpdate, db: Session = Depends(get_db), user: User = Depends(require_assessment_writers)):
    iep, _ = _visible(db, iep_id, user)
    changes = {k: v for k, v in _changes(payload).items() if v is not None or k == "domain"}
    return iep_service.update_finding(db, iep, finding_id, changes)


@router.delete("/ieps/{iep_id}/findings/{finding_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_finding(iep_id: int, finding_id: int, db: Session = Depends(get_db), user: User = Depends(require_assessment_writers)):
    iep, _ = _visible(db, iep_id, user)
    iep_service.delete_finding(db, iep, finding_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/ieps/{iep_id}/findings/order", response_model=IepRead)
def order_findings(iep_id: int, payload: OrderBody, db: Session = Depends(get_db), user: User = Depends(require_assessment_writers)):
    iep, _ = _visible(db, iep_id, user)
    return _read(iep_service.reorder_findings(db, iep, payload.ids))


# --- Goals -----------------------------------------------------------------------------------


@router.post("/ieps/{iep_id}/goals", response_model=IepGoalRead, status_code=status.HTTP_201_CREATED)
def add_goal(iep_id: int, payload: IepGoalCreate, db: Session = Depends(get_db), user: User = Depends(require_assessment_writers)):
    iep, _ = _visible(db, iep_id, user)
    data = _changes(payload)
    goal_id = data.pop("goal_id", None)
    return iep_service.add_goal(db, iep, data, goal_id)


@router.patch("/ieps/{iep_id}/goals/{goal_id}", response_model=IepGoalRead)
def update_goal(iep_id: int, goal_id: int, payload: IepGoalFields, db: Session = Depends(get_db), user: User = Depends(require_assessment_writers)):
    iep, _ = _visible(db, iep_id, user)
    changes = _changes(payload)
    if changes.get("statement", "") is None:
        changes.pop("statement")  # the statement can't be cleared
    return iep_service.update_goal(db, iep, goal_id, changes)


@router.delete("/ieps/{iep_id}/goals/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_goal(iep_id: int, goal_id: int, db: Session = Depends(get_db), user: User = Depends(require_assessment_writers)):
    iep, _ = _visible(db, iep_id, user)
    iep_service.delete_goal(db, iep, goal_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/ieps/{iep_id}/goals/order", response_model=IepRead)
def order_goals(iep_id: int, payload: OrderBody, db: Session = Depends(get_db), user: User = Depends(require_assessment_writers)):
    iep, _ = _visible(db, iep_id, user)
    return _read(iep_service.reorder_goals(db, iep, payload.ids))
