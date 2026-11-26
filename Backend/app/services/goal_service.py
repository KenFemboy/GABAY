"""Goal bank: taxonomy, goals, versions and usage (Stage 7).

Versioning rule: editing a goal whose current version is USED (it has
``GoalUsage`` rows, e.g. it was put in an IEP) creates a new version and the
used one is never changed. An unused version is edited in place.

Later stages must call ``record_goal_usage`` when they reference a goal version.
"""

import re

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import APIError, conflict, not_found
from app.models.goal import (
    Goal,
    GoalDomain,
    GoalSkill,
    GoalStatus,
    GoalUsage,
    GoalVersion,
)
from app.models.user import User

ACTIVE = GoalStatus.ACTIVE.value
DRAFT = GoalStatus.DRAFT.value
ARCHIVED = GoalStatus.ARCHIVED.value

# Fields that make up a goal version's content.
VERSION_FIELDS = (
    "domain_id",
    "skill_id",
    "statement",
    "measurement_method",
    "target_value",
    "target_unit",
    "criterion",
    "grade_band",
)

DOMAIN_PREFIX = {
    "reading": "RD",
    "writing": "WR",
    "mathematics": "MA",
    "behavior_social": "BS",
    "communication": "CM",
    "motor": "MO",
    "self_help": "SH",
    "cognitive": "CG",
    "other": "OT",
}


def invalid(code: str, message: str) -> APIError:
    return APIError(422, code, message)


# --- Taxonomy ----------------------------------------------------------------


def list_domains(db: Session, *, include_inactive: bool) -> list[GoalDomain]:
    query = select(GoalDomain).order_by(GoalDomain.sort_order, GoalDomain.id)
    if not include_inactive:
        query = query.where(GoalDomain.is_active.is_(True))
    return list(db.scalars(query).unique())


def get_domain(db: Session, domain_id: int) -> GoalDomain:
    domain = db.get(GoalDomain, domain_id)
    if domain is None:
        raise not_found("Domain not found.")
    return domain


def get_skill(db: Session, skill_id: int) -> GoalSkill:
    skill = db.get(GoalSkill, skill_id)
    if skill is None:
        raise not_found("Skill not found.")
    return skill


def _commit_unique(db: Session, message: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise conflict("duplicate_code", message) from exc


def create_domain(db: Session, data: dict) -> GoalDomain:
    domain = GoalDomain(**data)
    db.add(domain)
    _commit_unique(db, "A domain with this code already exists.")
    db.refresh(domain)
    return domain


def update_domain(db: Session, domain: GoalDomain, changes: dict) -> GoalDomain:
    for key, value in changes.items():
        setattr(domain, key, value)
    db.commit()
    db.refresh(domain)
    return domain


def create_skill(db: Session, data: dict) -> GoalSkill:
    get_domain(db, data["domain_id"])
    skill = GoalSkill(**data)
    db.add(skill)
    _commit_unique(db, "A skill with this code already exists in this domain.")
    db.refresh(skill)
    return skill


def update_skill(db: Session, skill: GoalSkill, changes: dict) -> GoalSkill:
    if "domain_id" in changes and changes["domain_id"] != skill.domain_id:
        get_domain(db, changes["domain_id"])
        used = db.scalar(select(func.count(GoalVersion.id)).where(GoalVersion.skill_id == skill.id))
        if used:
            raise conflict("skill_in_use", "This skill is used by goals and cannot move to another domain.")
    for key, value in changes.items():
        setattr(skill, key, value)
    _commit_unique(db, "A skill with this code already exists in this domain.")
    db.refresh(skill)
    return skill


# --- Goals: reading ----------------------------------------------------------


def get_goal(db: Session, goal_id: int, *, manager: bool) -> Goal:
    goal = db.get(Goal, goal_id)
    if goal is None or (not manager and goal.status != ACTIVE):
        raise not_found("Goal not found.")
    return goal


def list_goals(
    db: Session,
    *,
    manager: bool,
    status: str | None = None,
    domain_id: int | None = None,
    skill_id: int | None = None,
    grade_band: str | None = None,
    method: str | None = None,
    q: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[Goal], int]:
    query = select(Goal).join(GoalVersion, GoalVersion.id == Goal.current_version_id)
    if not manager:
        query = query.where(Goal.status == ACTIVE)
    elif status:
        query = query.where(Goal.status == status)
    if domain_id:
        query = query.where(GoalVersion.domain_id == domain_id)
    if skill_id:
        query = query.where(GoalVersion.skill_id == skill_id)
    if grade_band:
        query = query.where(or_(GoalVersion.grade_band == grade_band, GoalVersion.grade_band == "any"))
    if method:
        query = query.where(GoalVersion.measurement_method == method)
    if q:
        like = f"%{q.strip().lower()}%"
        query = query.where(
            or_(
                func.lower(GoalVersion.statement).like(like),
                func.lower(Goal.code).like(like),
                func.lower(func.coalesce(GoalVersion.criterion, "")).like(like),
            )
        )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(query.order_by(Goal.code).offset(offset).limit(limit)).unique()
    return list(items), total


def is_used(version: GoalVersion) -> bool:
    return bool(version.usages)


# --- Goals: writing ----------------------------------------------------------


def _check_taxonomy(db: Session, domain_id: int, skill_id: int, *, require_active: bool) -> None:
    domain = db.get(GoalDomain, domain_id)
    skill = db.get(GoalSkill, skill_id)
    if domain is None:
        raise invalid("invalid_domain", "The domain does not exist.")
    if skill is None or skill.domain_id != domain_id:
        raise invalid("invalid_skill", "The skill does not belong to the chosen domain.")
    if require_active and not (domain.is_active and skill.is_active):
        raise invalid("inactive_taxonomy", "The goal's domain or skill is no longer active.")


def _next_code(db: Session, domain: GoalDomain) -> str:
    prefix = DOMAIN_PREFIX.get(domain.code, domain.code[:2].upper())
    codes = db.scalars(select(Goal.code).where(Goal.code.like(f"{prefix}-%"))).all()
    numbers = [int(m.group(1)) for c in codes if (m := re.fullmatch(rf"{prefix}-(\d+)", c))]
    return f"{prefix}-{(max(numbers, default=0) + 1):03d}"


def create_goal(db: Session, user: User | None, data: dict, *, code: str | None = None) -> Goal:
    _check_taxonomy(db, data["domain_id"], data["skill_id"], require_active=False)
    domain = db.get(GoalDomain, data["domain_id"])
    goal = Goal(code=(code or _next_code(db, domain)).upper(), status=DRAFT, created_by=user.id if user else None)
    version = GoalVersion(
        version_number=1,
        created_by=user.id if user else None,
        change_note=data.get("change_note"),
        **{k: data.get(k) for k in VERSION_FIELDS},
    )
    goal.versions.append(version)
    db.add(goal)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise conflict("duplicate_code", "A goal with this code already exists.") from exc
    goal.current_version = version
    db.commit()
    db.refresh(goal)
    return goal


def update_goal(db: Session, user: User, goal: Goal, changes: dict) -> tuple[Goal, bool]:
    """Apply content changes. Returns (goal, created_new_version)."""
    if goal.status == ARCHIVED:
        raise conflict("goal_archived", "Archived goals cannot be edited. Activate it first.")
    current = goal.current_version
    content = {k: v for k, v in changes.items() if k in VERSION_FIELDS}
    merged = {k: content.get(k, getattr(current, k)) for k in VERSION_FIELDS}
    if all(merged[k] == getattr(current, k) for k in VERSION_FIELDS):
        return goal, False  # nothing changed
    _check_taxonomy(db, merged["domain_id"], merged["skill_id"], require_active=goal.status == ACTIVE)

    if is_used(current):
        version = GoalVersion(
            version_number=max(v.version_number for v in goal.versions) + 1,
            created_by=user.id,
            change_note=changes.get("change_note"),
            **merged,
        )
        goal.versions.append(version)
        db.flush()
        goal.current_version = version
        new_version = True
    else:
        for key, value in merged.items():
            setattr(current, key, value)
        if "change_note" in changes:
            current.change_note = changes["change_note"]
        new_version = False
    goal.updated_at = func.now()
    db.commit()
    db.refresh(goal)
    return goal, new_version


def activate(db: Session, goal: Goal) -> Goal:
    if goal.status == ACTIVE:
        return goal
    v = goal.current_version
    missing = [
        name
        for name, value in (
            ("statement", v.statement and v.statement.strip()),
            ("measurement method", v.measurement_method),
            ("target", v.target_value is not None and v.target_unit),
        )
        if not value
    ]
    if missing:
        raise invalid("goal_incomplete", f"The goal is missing: {', '.join(missing)}.")
    _check_taxonomy(db, v.domain_id, v.skill_id, require_active=True)
    goal.status = ACTIVE
    db.commit()
    db.refresh(goal)
    return goal


def archive(db: Session, goal: Goal) -> Goal:
    goal.status = ARCHIVED
    db.commit()
    db.refresh(goal)
    return goal


def delete_goal(db: Session, goal: Goal) -> None:
    if goal.status != DRAFT:
        raise conflict("goal_not_draft", "Only draft goals can be deleted. Archive it instead.")
    if any(v.usages for v in goal.versions):
        raise conflict("goal_in_use", "This goal is in use and cannot be deleted.")
    goal.current_version = None
    db.flush()
    db.delete(goal)
    db.commit()


# --- Usage (for later stages) --------------------------------------------------


def record_goal_usage(db: Session, goal_version_id: int, usage_type: str, reference_id: int) -> GoalUsage:
    """Mark a goal version as used (e.g. by an IEP). Idempotent. Does not commit."""
    existing = db.scalar(
        select(GoalUsage).where(
            GoalUsage.goal_version_id == goal_version_id,
            GoalUsage.usage_type == usage_type,
            GoalUsage.reference_id == reference_id,
        )
    )
    if existing is not None:
        return existing
    if db.get(GoalVersion, goal_version_id) is None:
        raise not_found("Goal version not found.")
    usage = GoalUsage(goal_version_id=goal_version_id, usage_type=usage_type, reference_id=reference_id)
    db.add(usage)
    db.flush()
    db.expire_all()  # refresh cached version.usages
    return usage
