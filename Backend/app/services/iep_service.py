"""IEP builder (Stage 9): drafts, import, validation, finalize, amendments.

Rules:
* One learner + school year has a series of versions (v1, v2, ...).
* At most one DRAFT per learner and school year.
* Every mutating function calls ``_require_draft``: finalized and superseded
  IEPs are read-only in the API (409 ``iep_read_only``).
* Finalizing runs ``validate`` first (422 ``iep_invalid`` with details).
* An amendment copies a finalized version into v(N+1) as a draft; finalizing
  the amendment marks the old version ``superseded``.
"""

from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import APIError, conflict, not_found
from app.models.extraction import ExtractionFinding
from app.models.goal import Goal, GoalStatus
from app.models.iep import Iep, IepFinding, IepGoal, IepGoalSource, IepStatus
from app.models.learner import Learner
from app.models.user import User
from app.services import extraction_service, goal_service, learner_service, matching_service
from app.services.extraction.schema import FindingCategory

DRAFT = IepStatus.DRAFT.value
FINALIZED = IepStatus.FINALIZED.value
SUPERSEDED = IepStatus.SUPERSEDED.value

IEP_FIELDS = ("start_date", "end_date", "annual_review_date", "accommodations", "services", "notes",
              "team_members", "amendment_reason")
GOAL_FIELDS = ("domain", "skill_name", "statement", "measurement_method", "baseline", "baseline_value",
               "target_value", "target_unit", "criterion", "responsible_staff", "start_date", "target_date",
               "review_dates", "addresses_finding_id")
FINDING_FIELDS = ("category", "domain", "text")


def _now() -> datetime:
    return datetime.now(UTC)


# --- Dates -----------------------------------------------------------------------------


def school_year_period(school_year: str) -> tuple[date, date]:
    """'2025-2026' -> (1 June 2025, 31 May 2026). Assumes a June-May school year."""
    first = int(school_year[:4])
    return date(first, 6, 1), date(first + 1, 5, 31)


def default_period(school_year: str, today: date | None = None) -> tuple[date, date]:
    sy_start, sy_end = school_year_period(school_year)
    today = today or date.today()
    start = today if sy_start <= today < sy_end else sy_start
    return start, sy_end


def quarterly_reviews(start: date, end: date) -> list[str]:
    """Three checkpoints at 1/4, 2/4, 3/4 of the period plus the end date."""
    span = (end - start).days
    return [(start + timedelta(days=round(span * i / 4))).isoformat() for i in (1, 2, 3, 4)]


# --- Lookups ---------------------------------------------------------------------------


def get_iep(db: Session, iep_id: int) -> Iep:
    iep = db.get(Iep, iep_id)
    if iep is None:
        raise not_found("IEP not found.")
    return iep


def history(db: Session, learner_id: int) -> list[Iep]:
    return list(
        db.scalars(
            select(Iep)
            .where(Iep.learner_id == learner_id)
            .order_by(Iep.school_year.desc(), Iep.version_number.desc())
        ).unique()
    )


def _draft_for(db: Session, learner_id: int, school_year: str) -> Iep | None:
    return db.scalar(
        select(Iep).where(Iep.learner_id == learner_id, Iep.school_year == school_year, Iep.status == DRAFT)
    )


def _require_draft(iep: Iep) -> None:
    if iep.status != DRAFT:
        raise conflict(
            "iep_read_only",
            "This IEP is finalized and cannot be changed. Start an amendment to make changes.",
        )


def _get_child(items, child_id: int, label: str):
    for item in items:
        if item.id == child_id:
            return item
    raise not_found(f"{label} not found.")


# --- Create / import ---------------------------------------------------------------------


def create_draft(db: Session, user: User, learner: Learner) -> tuple[Iep, dict[str, int]]:
    year = learner.school_year
    if _draft_for(db, learner.id, year) is not None:
        raise conflict("draft_exists", "This learner already has a draft IEP for this school year.")
    if db.scalar(select(Iep.id).where(Iep.learner_id == learner.id, Iep.school_year == year, Iep.status == FINALIZED)):
        raise conflict("iep_exists", "A finalized IEP exists for this school year. Amend it instead.")
    start, end = default_period(year)
    iep = Iep(
        learner_id=learner.id,
        school_year=year,
        version_number=1,
        status=DRAFT,
        start_date=start,
        end_date=end,
        annual_review_date=end - timedelta(days=14),
        team_members=[],
        created_by=user.id,
    )
    db.add(iep)
    db.flush()
    counts = import_sources(db, iep, commit=False)
    db.commit()
    db.refresh(iep)
    return iep, counts


def _baseline_hint(need: ExtractionFinding | None, present_levels: dict[str, str]) -> str | None:
    if need is None:
        return None
    level = present_levels.get(need.domain or "")
    return f"From assessment: {level or need.text}"


def import_sources(db: Session, iep: Iep, *, commit: bool = True) -> dict[str, int]:
    """Copy approved findings and accepted goals that are not in the IEP yet. Idempotent."""
    _require_draft(iep)
    findings = extraction_service.approved_findings_for_learner(db, iep.learner_id)
    have_findings = {f.source_finding_id: f for f in iep.findings if f.source_finding_id}
    next_pos = max((f.position for f in iep.findings), default=-1) + 1
    added_findings = 0
    for finding in findings:
        if finding.id in have_findings:
            continue
        row = IepFinding(
            category=finding.category, domain=finding.domain, text=finding.text,
            position=next_pos, source_finding_id=finding.id,
        )
        iep.findings.append(row)
        have_findings[finding.id] = row
        next_pos += 1
        added_findings += 1
    db.flush()

    present_levels = {f.domain: f.text for f in findings if f.category == FindingCategory.PRESENT_LEVEL.value and f.domain}
    findings_by_id = {f.id: f for f in findings}
    have_recs = {g.goal_recommendation_id for g in iep.goals if g.goal_recommendation_id}
    goal_pos = max((g.position for g in iep.goals), default=-1) + 1
    added_goals = 0
    for rec in matching_service.selected_goals_for_learner(db, iep.learner_id):
        if rec.id in have_recs:
            continue
        version = rec.goal_version
        need = findings_by_id.get(rec.finding_id) if rec.finding_id else None
        snapshot = have_findings.get(rec.finding_id) if rec.finding_id else None
        goal = IepGoal(
            position=goal_pos,
            source=IepGoalSource.ACCEPTED_RECOMMENDATION.value,
            goal_recommendation_id=rec.id,
            goal_id=rec.goal_id,
            goal_version_id=rec.goal_version_id,
            addresses_finding_id=snapshot.id if snapshot else None,
            domain=version.domain.code,
            skill_name=version.skill.name,
            goal_code=rec.goal.code,
            statement=rec.final_statement,
            measurement_method=version.measurement_method,
            baseline=_baseline_hint(need, present_levels),
            target_value=rec.final_target_value,
            target_unit=version.target_unit,
            criterion=rec.final_criterion,
            start_date=iep.start_date,
            target_date=iep.end_date,
            review_dates=quarterly_reviews(iep.start_date, iep.end_date) if iep.start_date and iep.end_date else [],
            match_score=rec.score,
        )
        iep.goals.append(goal)
        db.flush()
        goal_service.record_goal_usage(db, rec.goal_version_id, "iep_goal", goal.id)
        goal_pos += 1
        added_goals += 1
    if commit:
        db.commit()
        db.refresh(iep)
    return {"findings_added": added_findings, "goals_added": added_goals}


# --- Editing (drafts only) -------------------------------------------------------------------


def _check_finding_link(iep: Iep, finding_id: int | None) -> None:
    if finding_id is not None and finding_id not in {f.id for f in iep.findings}:
        raise APIError(422, "invalid_finding", "The linked need must be one of this IEP's findings.")


def update_iep(db: Session, iep: Iep, changes: dict) -> Iep:
    _require_draft(iep)
    for key, value in changes.items():
        if key in IEP_FIELDS:
            setattr(iep, key, value)
    db.commit()
    db.refresh(iep)
    return iep


def add_finding(db: Session, iep: Iep, data: dict) -> IepFinding:
    _require_draft(iep)
    row = IepFinding(position=max((f.position for f in iep.findings), default=-1) + 1,
                     **{k: data.get(k) for k in FINDING_FIELDS})
    iep.findings.append(row)
    db.commit()
    db.refresh(row)
    return row


def update_finding(db: Session, iep: Iep, finding_id: int, changes: dict) -> IepFinding:
    _require_draft(iep)
    row = _get_child(iep.findings, finding_id, "Finding")
    for key, value in changes.items():
        if key in FINDING_FIELDS:
            setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


def delete_finding(db: Session, iep: Iep, finding_id: int) -> None:
    _require_draft(iep)
    row = _get_child(iep.findings, finding_id, "Finding")
    for goal in iep.goals:
        if goal.addresses_finding_id == row.id:
            goal.addresses_finding_id = None
    iep.findings.remove(row)
    db.commit()


def _reorder(items, ids: list[int]) -> None:
    by_id = {i.id: i for i in items}
    if sorted(ids) != sorted(by_id):
        raise APIError(422, "invalid_order", "The order must list every item exactly once.")
    for position, item_id in enumerate(ids):
        by_id[item_id].position = position


def reorder_findings(db: Session, iep: Iep, ids: list[int]) -> Iep:
    _require_draft(iep)
    _reorder(iep.findings, ids)
    db.commit()
    db.expire(iep, ["findings"])
    return iep


def add_goal(db: Session, iep: Iep, data: dict, goal_id: int | None) -> IepGoal:
    """From the goal bank (goal_id) or a custom goal written for this IEP."""
    _require_draft(iep)
    _check_finding_link(iep, data.get("addresses_finding_id"))
    fields = {k: data.get(k) for k in GOAL_FIELDS if k in data}
    if goal_id is not None:
        bank_goal = db.get(Goal, goal_id)
        if bank_goal is None or bank_goal.status != GoalStatus.ACTIVE.value:
            raise APIError(422, "invalid_goal", "Choose an active goal from the goal bank.")
        v = bank_goal.current_version
        base = {
            "domain": v.domain.code, "skill_name": v.skill.name, "statement": v.statement,
            "measurement_method": v.measurement_method, "target_value": v.target_value,
            "target_unit": v.target_unit, "criterion": v.criterion,
        }
        fields = {**base, **{k: val for k, val in fields.items() if val is not None}}
        source, goal_code, version_id = IepGoalSource.GOAL_BANK.value, bank_goal.code, v.id
    else:
        if not (fields.get("statement") or "").strip():
            raise APIError(422, "statement_required", "A custom goal needs a statement.")
        source, goal_code, version_id = IepGoalSource.CUSTOM.value, None, None
    fields.setdefault("start_date", iep.start_date)
    fields.setdefault("target_date", iep.end_date)
    if not fields.get("review_dates") and iep.start_date and iep.end_date:
        fields["review_dates"] = quarterly_reviews(iep.start_date, iep.end_date)
    goal = IepGoal(
        position=max((g.position for g in iep.goals), default=-1) + 1,
        source=source,
        goal_id=goal_id,
        goal_version_id=version_id,
        goal_code=goal_code,
        **{**{"review_dates": []}, **fields},
    )
    iep.goals.append(goal)
    db.flush()
    if version_id is not None:
        goal_service.record_goal_usage(db, version_id, "iep_goal", goal.id)
    db.commit()
    db.refresh(goal)
    return goal


def update_goal(db: Session, iep: Iep, goal_id: int, changes: dict) -> IepGoal:
    _require_draft(iep)
    goal = _get_child(iep.goals, goal_id, "Goal")
    if "addresses_finding_id" in changes:
        _check_finding_link(iep, changes["addresses_finding_id"])
    for key, value in changes.items():
        if key in GOAL_FIELDS:
            setattr(goal, key, value)
    db.commit()
    db.refresh(goal)
    return goal


def delete_goal(db: Session, iep: Iep, goal_id: int) -> None:
    _require_draft(iep)
    iep.goals.remove(_get_child(iep.goals, goal_id, "Goal"))
    db.commit()


def reorder_goals(db: Session, iep: Iep, ids: list[int]) -> Iep:
    _require_draft(iep)
    _reorder(iep.goals, ids)
    db.commit()
    db.expire(iep, ["goals"])
    return iep


def discard_draft(db: Session, iep: Iep) -> None:
    _require_draft(iep)
    db.delete(iep)
    db.commit()


# --- Validation / finalize / amend ---------------------------------------------------------------


@dataclass
class Issue:
    field: str
    message: str
    goal_id: int | None = None


def _parse(d) -> date | None:
    if d is None or isinstance(d, date):
        return d
    try:
        return date.fromisoformat(str(d))
    except ValueError:
        return None


def validate(iep: Iep) -> list[Issue]:
    issues: list[Issue] = []
    start, end, review = iep.start_date, iep.end_date, iep.annual_review_date
    if not start:
        issues.append(Issue("start_date", "Set the IEP start date."))
    if not end:
        issues.append(Issue("end_date", "Set the IEP end date."))
    if start and end and end <= start:
        issues.append(Issue("end_date", "The end date must be after the start date."))
    if not review:
        issues.append(Issue("annual_review_date", "Set the annual review date."))
    elif start and end and not (start <= review <= end):
        issues.append(Issue("annual_review_date", "The annual review date must be within the IEP period."))
    if iep.version_number > 1 and not (iep.amendment_reason or "").strip():
        issues.append(Issue("amendment_reason", "State the reason for this amendment."))
    if not any(f.category in (FindingCategory.PRESENT_LEVEL.value, FindingCategory.NEED.value) for f in iep.findings):
        issues.append(Issue("findings", "Add at least one present level or need."))
    members = [m for m in (iep.team_members or []) if (m.get("name") or "").strip() and (m.get("role") or "").strip()]
    if not members:
        issues.append(Issue("team_members", "Add at least one IEP team member with a name and role."))
    if not iep.goals:
        issues.append(Issue("goals", "Add at least one goal."))

    for n, goal in enumerate(iep.goals, 1):
        label = f"Goal {n}"

        def bad(field: str, message: str, goal=goal, label=label) -> None:
            issues.append(Issue(f"goals.{goal.id}.{field}", f"{label}: {message}", goal.id))

        if len((goal.statement or "").strip()) < 10:
            bad("statement", "write the goal statement.")
        if not goal.measurement_method:
            bad("measurement_method", "choose how progress is measured.")
        if not (goal.baseline or "").strip():
            bad("baseline", "describe the baseline (current performance).")
        if goal.target_value is None or not goal.target_unit:
            bad("target_value", "set the target value and unit.")
        if not (goal.responsible_staff or "").strip():
            bad("responsible_staff", "name the responsible staff.")
        if not goal.target_date:
            bad("target_date", "set the target date.")
        elif start and end and not (start <= goal.target_date <= end):
            bad("target_date", "the target date must be within the IEP period.")
        if goal.start_date and goal.target_date and goal.start_date > goal.target_date:
            bad("start_date", "the start date must be before the target date.")
        reviews = [_parse(d) for d in (goal.review_dates or [])]
        if not reviews:
            bad("review_dates", "add at least one progress review date.")
        elif any(r is None for r in reviews):
            bad("review_dates", "a review date is not a valid date.")
        else:
            if start and end and any(not (start <= r <= end) for r in reviews):
                bad("review_dates", "review dates must be within the IEP period.")
            if goal.target_date and any(r > goal.target_date for r in reviews):
                bad("review_dates", "review dates must be on or before the target date.")
    return issues


def issues_payload(issues: list[Issue]) -> list[dict]:
    return [asdict(i) for i in issues]


def finalize(db: Session, user: User, iep: Iep) -> Iep:
    _require_draft(iep)
    issues = validate(iep)
    if issues:
        raise APIError(
            422, "iep_invalid", "The IEP is not complete yet. Fix the listed items, then finalize.",
            details=[{"field": i.field, "message": i.message} for i in issues],
        )
    if iep.amends_iep_id:
        previous = db.get(Iep, iep.amends_iep_id)
        if previous is not None and previous.status == FINALIZED:
            previous.status = SUPERSEDED
    iep.status = FINALIZED
    iep.finalized_by = user.id
    iep.finalized_at = _now()
    db.commit()
    db.refresh(iep)
    return iep


def amend(db: Session, user: User, iep: Iep, reason: str) -> Iep:
    if iep.status != FINALIZED:
        raise conflict("not_current", "Only the current finalized IEP can be amended.")
    if _draft_for(db, iep.learner_id, iep.school_year) is not None:
        raise conflict("draft_exists", "An amendment draft already exists. Finish or discard it first.")
    next_number = (
        db.scalar(
            select(func.max(Iep.version_number)).where(
                Iep.learner_id == iep.learner_id, Iep.school_year == iep.school_year
            )
        )
        or 0
    ) + 1
    copy = Iep(
        learner_id=iep.learner_id,
        school_year=iep.school_year,
        version_number=next_number,
        status=DRAFT,
        amends_iep_id=iep.id,
        amendment_reason=reason,
        start_date=iep.start_date,
        end_date=iep.end_date,
        annual_review_date=iep.annual_review_date,
        accommodations=iep.accommodations,
        services=iep.services,
        notes=iep.notes,
        team_members=[dict(m) for m in (iep.team_members or [])],
        created_by=user.id,
    )
    finding_map: dict[int, IepFinding] = {}
    for f in iep.findings:
        new = IepFinding(category=f.category, domain=f.domain, text=f.text, position=f.position,
                         source_finding_id=f.source_finding_id)
        copy.findings.append(new)
        finding_map[f.id] = new
    db.add(copy)
    db.flush()
    for g in iep.goals:
        linked = finding_map.get(g.addresses_finding_id) if g.addresses_finding_id else None
        new_goal = IepGoal(
            position=g.position, source=g.source, goal_recommendation_id=g.goal_recommendation_id,
            goal_id=g.goal_id, goal_version_id=g.goal_version_id,
            addresses_finding_id=linked.id if linked else None,
            domain=g.domain, skill_name=g.skill_name, goal_code=g.goal_code, statement=g.statement,
            measurement_method=g.measurement_method, baseline=g.baseline, baseline_value=g.baseline_value,
            target_value=g.target_value, target_unit=g.target_unit, criterion=g.criterion,
            responsible_staff=g.responsible_staff, start_date=g.start_date, target_date=g.target_date,
            review_dates=list(g.review_dates or []), match_score=g.match_score,
        )
        copy.goals.append(new_goal)
        db.flush()
        if new_goal.goal_version_id:
            goal_service.record_goal_usage(db, new_goal.goal_version_id, "iep_goal", new_goal.id)
    db.commit()
    db.refresh(copy)
    return copy


# --- Learner profile summary -----------------------------------------------------------------------


def summary_for_learner(db: Session, learner_id: int) -> tuple[int, str | None, datetime | None]:
    rows = history(db, learner_id)
    current = next((i for i in rows if i.status in (DRAFT, FINALIZED)), rows[0] if rows else None)
    if current is None:
        return 0, None, None
    return len(rows), current.status, current.updated_at


learner_service.MODULE_COUNTERS["iep"] = summary_for_learner
