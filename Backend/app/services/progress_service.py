"""Progress records (Stage 11): validation against the goal's measurement type,
goal progress, the combined timeline and the attention list.
"""

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import APIError, conflict, not_found
from app.models.iep import Iep, IepGoal, IepStatus
from app.models.ilaw import IlawEntry
from app.models.learner import Learner
from app.models.progress import EvidenceType, ProgressRecord, ProgressUnit
from app.models.user import User
from app.services import ilaw_alignment_service, learner_service
from app.services.progress_analysis import ATTENTION, SEVERITY, GoalStatus, Point, goal_status

GOAL_TYPES = {EvidenceType.PROBE.value, EvidenceType.WORK_SAMPLE.value, EvidenceType.TEST.value}

# Allowed range and whole-number rule per measurement method.
METHOD_RULES: dict[str, dict] = {
    "percent_accuracy": {"min": 0, "max": 100, "integer": False},
    "checklist": {"min": 0, "max": 100, "integer": False},
    "trials": {"min": 0, "max": 50, "integer": False},
    "frequency": {"min": 0, "max": 1000, "integer": True},
    "duration": {"min": 0, "max": 480, "integer": False, "exclusive_min": True},
    "rate": {"min": 0, "max": 400, "integer": False, "exclusive_min": True},
    "rubric": {"min": 0, "max": 10, "integer": True},
}


def _invalid(details: list[dict]) -> APIError:
    return APIError(422, "invalid_progress", "Check the highlighted fields.", details=details)


def get_record(db: Session, record_id: int) -> ProgressRecord:
    record = db.get(ProgressRecord, record_id)
    if record is None:
        raise not_found("Progress record not found.")
    return record


def _active_goal(iep: Iep, goal_id: int) -> IepGoal:
    for goal in iep.goals:
        if goal.id == goal_id:
            return goal
    raise _invalid([{"field": "iep_goal_id", "message": "Choose a goal from the learner's active IEP."}])


def validate(iep: Iep, data: dict) -> dict:
    """Return cleaned fields or raise 422 with per-field details."""
    errors: list[dict] = []
    kind = data["evidence_type"]
    goal = _active_goal(iep, data["iep_goal_id"]) if data.get("iep_goal_id") else None
    value = data.get("value")
    out_of = data.get("out_of")
    correct, total = data.get("correct"), data.get("total")
    clean = {k: data.get(k) for k in ("evidence_type", "iep_goal_id", "ilaw_entry_id", "recorded_on", "note",
                                      "subject", "grading_period")}
    clean["value"], clean["out_of"], clean["unit"] = None, None, None

    recorded_on: date = data["recorded_on"]
    if recorded_on > date.today():
        errors.append({"field": "recorded_on", "message": "The date cannot be in the future."})
    elif iep.start_date and iep.end_date and not (iep.start_date <= recorded_on <= iep.end_date):
        errors.append({"field": "recorded_on", "message": "The date must be within the IEP period."})

    if kind in GOAL_TYPES and goal is None:
        errors.append({"field": "iep_goal_id", "message": "Choose the goal this evidence measures."})
    if kind == EvidenceType.OBSERVATION.value and not (data.get("note") or "").strip():
        errors.append({"field": "note", "message": "Describe what was observed."})

    if kind == EvidenceType.GRADE.value:
        if not (data.get("subject") or "").strip():
            errors.append({"field": "subject", "message": "Enter the subject."})
        if not data.get("grading_period"):
            errors.append({"field": "grading_period", "message": "Choose the grading period."})
        if value is None or not (0 <= value <= 100):
            errors.append({"field": "value", "message": "Enter a grade from 0 to 100."})
        clean.update(value=value, unit=ProgressUnit.GRADE.value)
    else:
        clean["subject"] = clean["grading_period"] = None
        # Convert correct/total to a percentage when given.
        if value is None and correct is not None and total:
            if not (0 <= correct <= total):
                errors.append({"field": "correct", "message": "Correct answers must be between 0 and the total."})
            else:
                value = round(100 * correct / total, 1)
        if goal is not None and (value is not None or kind in GOAL_TYPES):
            method = goal.measurement_method or ""
            unit = goal.target_unit
            if data.get("unit") and data["unit"] != unit:
                errors.append({"field": "unit", "message": f"This goal is measured in '{unit}'."})
            if value is None:
                errors.append({"field": "value", "message": "Enter the measured value."})
            else:
                rule = METHOD_RULES.get(method)
                if rule:
                    low_ok = value > rule["min"] if rule.get("exclusive_min") else value >= rule["min"]
                    if not low_ok or value > rule["max"]:
                        bound = ">" if rule.get("exclusive_min") else "≥"
                        errors.append({"field": "value", "message": f"Enter a value {bound} {rule['min']} and ≤ {rule['max']}."})
                    if rule["integer"] and float(value) != int(value):
                        errors.append({"field": "value", "message": "Enter a whole number."})
                if method == "trials":
                    if out_of is None or out_of <= 0:
                        errors.append({"field": "out_of", "message": "Enter how many trials were given."})
                    elif value > out_of:
                        errors.append({"field": "value", "message": "Successful trials cannot exceed the number of trials."})
                    clean["out_of"] = out_of
            clean.update(value=value, unit=unit)
        elif value is not None:
            errors.append({"field": "iep_goal_id", "message": "Link a goal to record a measured value."})

    if errors:
        raise _invalid(errors)
    return clean


def _check_ilaw(db: Session, learner: Learner, entry_id: int | None) -> None:
    if entry_id is None:
        return
    entry = db.get(IlawEntry, entry_id)
    if entry is None or entry.learner_id != learner.id:
        raise _invalid([{"field": "ilaw_entry_id", "message": "Choose one of this learner's activity entries."}])


def create(db: Session, user: User, learner: Learner, data: dict) -> ProgressRecord:
    iep = ilaw_alignment_service.active_iep(db, learner)
    if iep is None:
        raise conflict("no_active_iep", "Finalize the learner's IEP before recording progress.")
    clean = validate(iep, data)
    _check_ilaw(db, learner, clean.get("ilaw_entry_id"))
    record = ProgressRecord(learner_id=learner.id, iep_id=iep.id, created_by=user.id, **clean)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def update(db: Session, record: ProgressRecord, learner: Learner, changes: dict) -> ProgressRecord:
    iep = db.get(Iep, record.iep_id)
    merged = {
        "evidence_type": record.evidence_type, "iep_goal_id": record.iep_goal_id, "ilaw_entry_id": record.ilaw_entry_id,
        "recorded_on": record.recorded_on, "note": record.note, "subject": record.subject,
        "grading_period": record.grading_period, "value": record.value, "out_of": record.out_of, "unit": record.unit,
    }
    if "correct" in changes or "total" in changes:
        merged["value"] = None
    merged.update(changes)
    clean = validate(iep, merged)
    _check_ilaw(db, learner, clean.get("ilaw_entry_id"))
    for key, value in clean.items():
        setattr(record, key, value)
    db.commit()
    db.refresh(record)
    return record


def delete(db: Session, record: ProgressRecord) -> None:
    db.delete(record)
    db.commit()


def list_records(db: Session, learner_id: int, *, kinds=None, goal_id=None, date_from=None, date_to=None):
    query = select(ProgressRecord).where(ProgressRecord.learner_id == learner_id)
    if kinds:
        query = query.where(ProgressRecord.evidence_type.in_(kinds))
    if goal_id:
        query = query.where(ProgressRecord.iep_goal_id == goal_id)
    if date_from:
        query = query.where(ProgressRecord.recorded_on >= date_from)
    if date_to:
        query = query.where(ProgressRecord.recorded_on <= date_to)
    return list(db.scalars(query.order_by(ProgressRecord.recorded_on.desc(), ProgressRecord.id.desc())).unique())


# --- Goal progress ------------------------------------------------------------------------------


@dataclass
class GoalProgress:
    goal: IepGoal
    number: int
    status: GoalStatus
    points: list[ProgressRecord]  # chartable (same unit as the goal), oldest first
    other: list[ProgressRecord]  # linked grades / observations without a chartable value
    aim_start: tuple[date, float] | None
    aim_end: tuple[date, float] | None


def _chartable(goal: IepGoal, record: ProgressRecord) -> bool:
    return record.value is not None and record.unit == goal.target_unit and record.evidence_type != EvidenceType.GRADE.value


def goal_progress(db: Session, goal: IepGoal, number: int, today: date | None = None) -> GoalProgress:
    today = today or date.today()
    records = sorted(
        db.scalars(select(ProgressRecord).where(ProgressRecord.iep_goal_id == goal.id)).unique(),
        key=lambda r: (r.recorded_on, r.id),
    )
    points = [r for r in records if _chartable(goal, r)]
    other = [r for r in records if not _chartable(goal, r)]
    status = goal_status(
        baseline=goal.baseline_value, target=goal.target_value, start=goal.start_date, end=goal.target_date,
        points=[Point(r.recorded_on, r.value) for r in points], today=today,
    )
    aim_start = aim_end = None
    if status.status != "no_baseline":
        aim_start = (goal.start_date, goal.baseline_value)
        aim_end = (goal.target_date, goal.target_value)
    return GoalProgress(goal, number, status, points, other, aim_start, aim_end)


def active_goal_progress(db: Session, learner: Learner) -> tuple[Iep | None, list[GoalProgress]]:
    iep = ilaw_alignment_service.active_iep(db, learner)
    if iep is None:
        return None, []
    return iep, [goal_progress(db, g, n) for n, g in enumerate(iep.goals, 1)]


def find_goal(db: Session, goal_id: int) -> tuple[IepGoal, int]:
    goal = db.get(IepGoal, goal_id)
    if goal is None:
        raise not_found("Goal not found.")
    number = next((n for n, g in enumerate(goal.iep.goals, 1) if g.id == goal.id), 1)
    return goal, number


# --- Timeline ---------------------------------------------------------------------------------------


TIMELINE_KINDS = ("ilaw", "probe", "work_sample", "test", "observation", "grade")


def timeline(db: Session, learner_id: int, *, kinds=None, date_from=None, date_to=None) -> list[dict]:
    kinds = set(kinds or TIMELINE_KINDS)
    items: list[dict] = []
    record_kinds = [k for k in kinds if k != "ilaw"]
    if record_kinds:
        for r in list_records(db, learner_id, kinds=record_kinds, date_from=date_from, date_to=date_to):
            items.append({
                "kind": r.evidence_type, "id": r.id, "date": r.recorded_on, "created_at": r.created_at,
                "title": r.subject if r.evidence_type == "grade" else None,
                "summary": r.note, "value": r.value, "out_of": r.out_of, "unit": r.unit,
                "grading_period": r.grading_period, "goal_ids": [r.iep_goal_id] if r.iep_goal_id else [],
                "created_by_name": r.created_by_name,
            })
    if "ilaw" in kinds:
        query = select(IlawEntry).where(IlawEntry.learner_id == learner_id)
        if date_from:
            query = query.where(IlawEntry.activity_date >= date_from)
        if date_to:
            query = query.where(IlawEntry.activity_date <= date_to)
        for e in db.scalars(query).unique():
            items.append({
                "kind": "ilaw", "id": e.id, "date": e.activity_date, "created_at": e.created_at,
                "title": e.title, "summary": e.learner_response or e.description, "value": None, "out_of": None,
                "unit": None, "grading_period": None,
                "goal_ids": [a.iep_goal_id for a in e.alignments if a.status == "confirmed"],
                "created_by_name": e.created_by_name,
            })
    items.sort(key=lambda i: (i["date"], i["created_at"] or datetime.min), reverse=True)
    return items


# --- Attention list -----------------------------------------------------------------------------------


def attention(db: Session, user: User, statuses: set[str] | None = None, today: date | None = None) -> list[dict]:
    statuses = statuses or set(ATTENTION)
    # Same visibility rules as everywhere else (Teachers: assigned learners only).
    visible_ids = learner_service.visible_learners_query(user).with_only_columns(Learner.id)
    query = (
        select(Iep, Learner)
        .join(Learner, Learner.id == Iep.learner_id)
        .where(
            Iep.status == IepStatus.FINALIZED.value,
            Iep.school_year == Learner.school_year,
            Learner.id.in_(visible_ids),
        )
    )
    rows = []
    for iep, learner in db.execute(query).unique().all():
        for number, goal in enumerate(iep.goals, 1):
            gp = goal_progress(db, goal, number, today)
            if gp.status.status in statuses:
                rows.append({"learner": learner, "iep": iep, "progress": gp})
    rows.sort(key=lambda r: (SEVERITY[r["progress"].status.status], -(r["progress"].status.gap or 0)))
    return rows


def summary_for_learner(db: Session, learner_id: int) -> tuple[int, str | None, datetime | None]:
    count = db.scalar(select(func.count(ProgressRecord.id)).where(ProgressRecord.learner_id == learner_id)) or 0
    latest = db.scalar(
        select(ProgressRecord.recorded_on).where(ProgressRecord.learner_id == learner_id)
        .order_by(ProgressRecord.recorded_on.desc()).limit(1)
    )
    return count, ("recorded" if count else None), (datetime.combine(latest, datetime.min.time()) if latest else None)


learner_service.MODULE_COUNTERS["progress"] = summary_for_learner

