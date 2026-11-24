from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.permissions import require_learner_editors, require_learner_readers
from app.db.session import get_db
from app.models.learner import GradeLevel, Learner, LearnerAssignment, LearnerStatus
from app.models.user import User
from app.schemas.learner import (
    AssignmentCreate,
    AssignmentRead,
    LearnerCreate,
    LearnerList,
    LearnerRead,
    LearnerSummary,
    LearnerUpdate,
)
from app.services import learner_service

router = APIRouter(prefix="/api/learners", tags=["learners"])


@router.get("", response_model=LearnerList)
def list_learners(
    search: str | None = Query(default=None, max_length=100),
    grade_level: GradeLevel | None = None,
    section: str | None = Query(default=None, max_length=50),
    school_year: str | None = Query(default=None, max_length=16),
    status_filter: LearnerStatus | None = Query(default=None, alias="status"),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(require_learner_readers),
) -> LearnerList:
    items, total = learner_service.list_learners(
        db,
        user,
        search=search,
        grade_level=grade_level,
        section=section,
        school_year=school_year,
        status=status_filter,
        offset=offset,
        limit=limit,
    )
    return LearnerList(items=[LearnerRead.model_validate(x) for x in items], total=total)


@router.post("", response_model=LearnerRead, status_code=status.HTTP_201_CREATED)
def create_learner(
    payload: LearnerCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_learner_editors),
) -> Learner:
    return learner_service.create_learner(db, payload)


@router.get("/{learner_id}", response_model=LearnerRead)
def get_learner(
    learner_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_learner_readers),
) -> Learner:
    return learner_service.get_visible_learner(db, learner_id, user)


@router.patch("/{learner_id}", response_model=LearnerRead)
def update_learner(
    learner_id: int,
    payload: LearnerUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_learner_editors),
) -> Learner:
    learner = learner_service.get_visible_learner(db, learner_id, user)
    return learner_service.update_learner(db, learner, payload)


@router.get("/{learner_id}/summary", response_model=LearnerSummary)
def get_learner_summary(
    learner_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_learner_readers),
) -> LearnerSummary:
    learner = learner_service.get_visible_learner(db, learner_id, user)
    return LearnerSummary(
        learner=LearnerRead.model_validate(learner),
        modules=learner_service.get_summary(db, learner),
    )


@router.get("/{learner_id}/assignments", response_model=list[AssignmentRead])
def list_assignments(
    learner_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_learner_readers),
) -> list[LearnerAssignment]:
    learner = learner_service.get_visible_learner(db, learner_id, user)
    return learner_service.list_assignments(db, learner)


@router.post(
    "/{learner_id}/assignments",
    response_model=AssignmentRead,
    status_code=status.HTTP_201_CREATED,
)
def add_assignment(
    learner_id: int,
    payload: AssignmentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_learner_editors),
) -> LearnerAssignment:
    learner = learner_service.get_visible_learner(db, learner_id, user)
    return learner_service.add_assignment(db, learner, payload)


@router.delete("/{learner_id}/assignments/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_assignment(
    learner_id: int,
    assignment_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_learner_editors),
) -> Response:
    learner = learner_service.get_visible_learner(db, learner_id, user)
    learner_service.remove_assignment(db, learner, assignment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
