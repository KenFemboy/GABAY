"""Learner records, row-level visibility and teacher assignments.

Every later module (assessments, IEP, ILAW, progress, evaluations) should call
``get_visible_learner`` before reading or writing rows for a ``learner_id`` so
the same access rules apply everywhere. Stage 14 audit logging hooks in here.
"""

from collections.abc import Callable
from datetime import datetime

from sqlalchemy import Select, exists, false, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import APIError, conflict, not_found
from app.models.learner import GradeLevel, Learner, LearnerAssignment, LearnerStatus
from app.models.user import Role, User, UserStatus
from app.schemas.learner import AssignmentCreate, LearnerCreate, LearnerUpdate, ModuleSummary

# Returned for both "does not exist" and "exists but you may not see it", so
# record IDs cannot be probed.
LEARNER_NOT_FOUND = "Learner not found."


def _code_taken() -> APIError:
    return conflict("learner_code_taken", "A learner with this code already exists.")


# --- Visibility --------------------------------------------------------------


def visible_learners_query(user: User) -> Select[tuple[Learner]]:
    """Base query limited to the learners ``user`` may see.

    Teachers see a learner only while assigned to them for the learner's
    current school year. Coordinators and School Heads see all learners.
    """
    query = select(Learner)
    if user.role == Role.TEACHER.value:
        query = query.where(
            exists().where(
                LearnerAssignment.learner_id == Learner.id,
                LearnerAssignment.user_id == user.id,
                LearnerAssignment.school_year == Learner.school_year,
            )
        )
    elif user.role not in {Role.SNED_COORDINATOR.value, Role.SCHOOL_HEAD.value}:
        query = query.where(false())
    return query


def get_visible_learner(db: Session, learner_id: int, user: User) -> Learner:
    learner = db.scalar(visible_learners_query(user).where(Learner.id == learner_id))
    if learner is None:
        raise not_found(LEARNER_NOT_FOUND)
    return learner


# --- Learners ----------------------------------------------------------------


def get_by_code(db: Session, code: str) -> Learner | None:
    return db.scalar(select(Learner).where(Learner.learner_code == code.strip().upper()))


def list_learners(
    db: Session,
    user: User,
    *,
    search: str | None = None,
    grade_level: GradeLevel | None = None,
    section: str | None = None,
    school_year: str | None = None,
    status: LearnerStatus | None = None,
    offset: int = 0,
    limit: int = 25,
) -> tuple[list[Learner], int]:
    query = visible_learners_query(user)
    if search and search.strip():
        pattern = f"%{search.strip().lower()}%"
        query = query.where(
            or_(
                func.lower(Learner.learner_code).like(pattern),
                func.lower(Learner.first_name).like(pattern),
                func.lower(Learner.last_name).like(pattern),
                func.lower(Learner.first_name + " " + Learner.last_name).like(pattern),
            )
        )
    if grade_level:
        query = query.where(Learner.grade_level == grade_level.value)
    if section and section.strip():
        query = query.where(func.lower(Learner.section) == section.strip().lower())
    if school_year and school_year.strip():
        query = query.where(Learner.school_year == school_year.strip())
    if status:
        query = query.where(Learner.status == status.value)

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.order_by(Learner.last_name, Learner.first_name, Learner.id).offset(offset).limit(limit)
    ).all()
    return list(items), total


def create_learner(db: Session, data: LearnerCreate) -> Learner:
    if get_by_code(db, data.learner_code):
        raise _code_taken()
    values = data.model_dump()
    for key in ("sex", "grade_level", "status"):
        values[key] = values[key].value
    learner = Learner(**values)
    db.add(learner)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _code_taken() from exc
    db.refresh(learner)
    return learner


def update_learner(db: Session, learner: Learner, data: LearnerUpdate) -> Learner:
    changes = data.model_dump(exclude_unset=True)
    new_code = changes.get("learner_code")
    if new_code is not None and new_code != learner.learner_code and get_by_code(db, new_code):
        raise _code_taken()

    for key, value in changes.items():
        setattr(learner, key, value.value if hasattr(value, "value") else value)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _code_taken() from exc
    db.refresh(learner)
    return learner


# --- Summary -----------------------------------------------------------------

# (count, latest_status, latest_at) for one learner.
ModuleCounter = Callable[[Session, int], tuple[int, str | None, datetime | None]]

# Each later stage registers its counter here, for example
#   MODULE_COUNTERS["assessments"] = assessment_service.summary_for_learner
# Order is the order shown on the learner profile.
MODULE_COUNTERS: dict[str, ModuleCounter | None] = {
    "assessments": None,
    "iep": None,
    "ilaw": None,
    "progress": None,
    "evaluations": None,
}


def get_summary(db: Session, learner: Learner) -> dict[str, ModuleSummary]:
    modules: dict[str, ModuleSummary] = {}
    for name, counter in MODULE_COUNTERS.items():
        if counter is None:
            modules[name] = ModuleSummary(available=False)
        else:
            count, latest_status, latest_at = counter(db, learner.id)
            modules[name] = ModuleSummary(
                available=True, count=count, latest_status=latest_status, latest_at=latest_at
            )
    return modules


# --- Assignments -------------------------------------------------------------


def list_assignments(db: Session, learner: Learner) -> list[LearnerAssignment]:
    return list(
        db.scalars(
            select(LearnerAssignment)
            .where(LearnerAssignment.learner_id == learner.id)
            .order_by(LearnerAssignment.school_year.desc(), LearnerAssignment.id)
        ).unique()
    )


def list_assignable_teachers(db: Session) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .where(User.role == Role.TEACHER.value, User.status == UserStatus.ACTIVE.value)
            .order_by(User.name, User.id)
        )
    )


def add_assignment(db: Session, learner: Learner, data: AssignmentCreate) -> LearnerAssignment:
    teacher = db.get(User, data.user_id)
    if teacher is None or teacher.role != Role.TEACHER.value or not teacher.is_active:
        raise APIError(400, "invalid_assignee", "Learners can only be assigned to active Teachers.")

    school_year = data.school_year or learner.school_year
    already_assigned = conflict(
        "already_assigned", "This teacher is already assigned to this learner for that school year."
    )
    duplicate = db.scalar(
        select(LearnerAssignment.id).where(
            LearnerAssignment.learner_id == learner.id,
            LearnerAssignment.user_id == teacher.id,
            LearnerAssignment.school_year == school_year,
        )
    )
    if duplicate is not None:
        raise already_assigned

    assignment = LearnerAssignment(learner_id=learner.id, user_id=teacher.id, school_year=school_year)
    db.add(assignment)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise already_assigned from exc
    db.refresh(assignment)
    return assignment


def remove_assignment(db: Session, learner: Learner, assignment_id: int) -> None:
    assignment = db.get(LearnerAssignment, assignment_id)
    if assignment is None or assignment.learner_id != learner.id:
        raise not_found("Assignment not found.")
    db.delete(assignment)
    db.commit()
