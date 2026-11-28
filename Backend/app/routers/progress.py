"""Progress monitoring API (Stage 11)."""

from datetime import date

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.permissions import require_assessment_writers, require_learner_readers
from app.db.session import get_db
from app.models.user import User
from app.schemas.progress import (
    AimPoint,
    AttentionList,
    AttentionRow,
    GoalBrief,
    GoalProgressRead,
    LearnerProgress,
    RecordCreate,
    RecordList,
    RecordRead,
    RecordUpdate,
    StatusRead,
    Timeline,
    TimelineItem,
)
from app.services import learner_service, progress_service
from app.services.progress_analysis import ATTENTION
from app.services.progress_service import TIMELINE_KINDS, GoalProgress

router = APIRouter(prefix="/api", tags=["progress"])


def _csv(value: str | None, allowed) -> list[str] | None:
    if not value:
        return None
    items = [v.strip() for v in value.split(",") if v.strip()]
    return [v for v in items if v in allowed] or None


def progress_read(gp: GoalProgress) -> GoalProgressRead:
    g = gp.goal
    return GoalProgressRead(
        goal=GoalBrief(id=g.id, number=gp.number, goal_code=g.goal_code, domain=g.domain, statement=g.statement,
                       measurement_method=g.measurement_method, target_unit=g.target_unit, criterion=g.criterion),
        baseline_value=g.baseline_value,
        baseline=g.baseline,
        target_value=g.target_value,
        start_date=g.start_date,
        target_date=g.target_date,
        review_dates=list(g.review_dates or []),
        status=StatusRead(**gp.status.__dict__),
        aim_start=AimPoint(date=gp.aim_start[0], value=gp.aim_start[1]) if gp.aim_start else None,
        aim_end=AimPoint(date=gp.aim_end[0], value=gp.aim_end[1]) if gp.aim_end else None,
        points=[RecordRead.model_validate(r) for r in gp.points],
        other=[RecordRead.model_validate(r) for r in gp.other],
    )


def _payload(model) -> dict:
    data = model.model_dump(exclude_unset=True)
    for key in ("evidence_type", "unit", "grading_period"):
        if key in data and data[key] is not None and hasattr(data[key], "value"):
            data[key] = data[key].value
    return data


@router.get("/learners/{learner_id}/progress/goals", response_model=LearnerProgress)
def learner_goal_progress(learner_id: int, db: Session = Depends(get_db), user: User = Depends(require_learner_readers)):
    learner = learner_service.get_visible_learner(db, learner_id, user)
    iep, goals = progress_service.active_goal_progress(db, learner)
    return LearnerProgress(
        iep_id=iep.id if iep else None,
        iep_version=iep.version_number if iep else None,
        goals=[progress_read(g) for g in goals],
    )


@router.get("/iep-goals/{goal_id}/progress", response_model=GoalProgressRead)
def one_goal_progress(goal_id: int, db: Session = Depends(get_db), user: User = Depends(require_learner_readers)):
    goal, number = progress_service.find_goal(db, goal_id)
    learner_service.get_visible_learner(db, goal.iep.learner_id, user)
    return progress_read(progress_service.goal_progress(db, goal, number))


@router.get("/learners/{learner_id}/progress", response_model=RecordList)
def list_records(
    learner_id: int,
    type: str | None = None,
    goal: int | None = None,
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
    user: User = Depends(require_learner_readers),
) -> RecordList:
    learner = learner_service.get_visible_learner(db, learner_id, user)
    kinds = _csv(type, {"probe", "work_sample", "test", "observation", "grade"})
    records = progress_service.list_records(db, learner.id, kinds=kinds, goal_id=goal, date_from=date_from, date_to=date_to)
    return RecordList(items=[RecordRead.model_validate(r) for r in records])


@router.post("/learners/{learner_id}/progress", response_model=RecordRead, status_code=status.HTTP_201_CREATED)
def create_record(learner_id: int, payload: RecordCreate, db: Session = Depends(get_db), user: User = Depends(require_assessment_writers)):
    learner = learner_service.get_visible_learner(db, learner_id, user)
    return progress_service.create(db, user, learner, _payload(payload))


@router.patch("/progress/{record_id}", response_model=RecordRead)
def update_record(record_id: int, payload: RecordUpdate, db: Session = Depends(get_db), user: User = Depends(require_assessment_writers)):
    record = progress_service.get_record(db, record_id)
    learner = learner_service.get_visible_learner(db, record.learner_id, user)
    return progress_service.update(db, record, learner, _payload(payload))


@router.delete("/progress/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_record(record_id: int, db: Session = Depends(get_db), user: User = Depends(require_assessment_writers)):
    record = progress_service.get_record(db, record_id)
    learner_service.get_visible_learner(db, record.learner_id, user)
    progress_service.delete(db, record)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/learners/{learner_id}/timeline", response_model=Timeline)
def learner_timeline(
    learner_id: int,
    types: str | None = None,
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    db: Session = Depends(get_db),
    user: User = Depends(require_learner_readers),
) -> Timeline:
    learner = learner_service.get_visible_learner(db, learner_id, user)
    items = progress_service.timeline(db, learner.id, kinds=_csv(types, TIMELINE_KINDS), date_from=date_from, date_to=date_to)
    return Timeline(items=[TimelineItem(**{k: v for k, v in i.items() if k != "created_at"}) for i in items])


@router.get("/progress/attention", response_model=AttentionList)
def attention_list(
    status_: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    user: User = Depends(require_learner_readers),
) -> AttentionList:
    statuses = set(_csv(status_, ATTENTION) or ATTENTION)
    rows = progress_service.attention(db, user, statuses)
    return AttentionList(items=[
        AttentionRow(
            learner_id=r["learner"].id, learner_name=r["learner"].full_name, learner_code=r["learner"].learner_code,
            grade_level=r["learner"].grade_level, section=r["learner"].section, iep_id=r["iep"].id,
            progress=progress_read(r["progress"]),
        )
        for r in rows
    ])
