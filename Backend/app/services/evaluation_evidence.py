"""Build the DE-IDENTIFIED evidence package for a year-end evaluation (Stage 12).

The package is what staff preview and, if they choose, what is sent to OpenAI.
Every item has a stable evidence ID the model must cite:

    G1..Gn  goals of the active IEP (IEP order)    F<id>  approved findings
    P<id>   progress data points / tests / samples  A<id>  ILAW activities
    O<id>   observations                             R<id>  grades

De-identification: learner names become [LEARNER], staff names [STAFF], the
school name [SCHOOL]; learner code, birth date, emails, phone numbers and
calendar dates are never included (dates become "week N" of the IEP).
``assert_clean`` re-scans the final text and refuses to continue if any
identifier is still present (fail closed).
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import APIError, conflict
from app.models.ilaw import IlawEntry
from app.models.iep import Iep
from app.models.learner import Learner
from app.models.progress import ProgressRecord
from app.models.user import User
from app.services import extraction_service, ilaw_alignment_service, progress_service

MAX_POINTS_PER_GOAL = 20
MAX_ACTIVITIES_PER_GOAL = 5
GRADE_NAMES = {"K": "Kindergarten", "NG": "Non-graded"}

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"(?<!\w)(?:\+?63|0)9\d{2}[\s-]?\d{3}[\s-]?\d{4}(?!\w)|(?<!\w)\d{3}[\s-]\d{3,4}[\s-]\d{4}(?!\w)")
ISO_DATE = re.compile(r"\b(19|20)\d{2}-\d{2}-\d{2}\b")


class IdentifierLeak(Exception):
    pass


@dataclass
class EvidencePackage:
    package: dict
    ids: list[str]
    hash: str
    goal_ids: dict[str, int]  # "G1" -> iep_goal id
    goal_status: dict[str, str]  # "G1" -> progress status
    learner_terms: list[str] = field(default_factory=list)
    staff_terms: list[str] = field(default_factory=list)
    first_name: str = ""
    iep_id: int | None = None


# --- Scrubbing ---------------------------------------------------------------------------


def _terms(names: list[str], min_len: int = 3) -> list[str]:
    """Full names plus their individual words (longest first, so full names win).

    Full names are matched case-insensitively; single words only when written
    Capitalised, like a name - so a learner called "Will" does not scrub every
    "the learner will ...".
    """
    out: set[str] = set()
    for name in names:
        name = (name or "").strip()
        if not name:
            continue
        out.add(name)
        out.update(w for w in re.split(r"[\s.,]+", name) if len(w) >= min_len)
    return sorted(out, key=len, reverse=True)


def _pattern(term: str) -> re.Pattern:
    body = re.escape(term)
    if " " in term:
        return re.compile(rf"(?<![\w]){body}(?![\w])", re.IGNORECASE)
    # Single word: match as written with a capital first letter (any case after it).
    head, tail = term[0], term[1:]
    return re.compile(rf"(?<![\w]){re.escape(head.upper())}(?i:{re.escape(tail)})(?![\w])")


def _replace_terms(text: str, terms: list[str], placeholder: str) -> str:
    for term in terms:
        text = _pattern(term).sub(placeholder, text)
    return text


class Scrubber:
    def __init__(self, learner: Learner, staff_names: list[str], school_name: str) -> None:
        self.learner_terms = _terms([learner.full_name, learner.first_name, learner.middle_name or "", learner.last_name])
        self.code = learner.learner_code
        self.birth = learner.birth_date.isoformat()
        self.staff_terms = [t for t in _terms(staff_names, 4) if t.lower() not in {t2.lower() for t2 in self.learner_terms}]
        self.school = school_name.strip()

    def __call__(self, text: str | None) -> str | None:
        if text is None:
            return None
        text = text.replace(self.code, "[CODE REMOVED]")
        text = text.replace(self.birth, "[DATE REMOVED]")
        if self.school and self.school.lower() not in {"sample school"}:
            text = _replace_terms(text, [self.school], "[SCHOOL]")
        text = _replace_terms(text, self.learner_terms, "[LEARNER]")
        text = _replace_terms(text, self.staff_terms, "[STAFF]")
        text = EMAIL.sub("[EMAIL REMOVED]", text)
        text = PHONE.sub("[PHONE REMOVED]", text)
        text = ISO_DATE.sub("[DATE REMOVED]", text)
        return text


def find_leaks(text: str, learner: Learner, staff_terms: list[str]) -> list[str]:
    """Identifiers still present in a text (empty list = clean)."""
    leaks = []
    for term in _terms([learner.full_name, learner.first_name, learner.last_name]):
        if _pattern(term).search(text):
            leaks.append("learner name")
            break
    if learner.learner_code.lower() in text.lower():
        leaks.append("learner code")
    if learner.birth_date.isoformat() in text:
        leaks.append("birth date")
    for term in staff_terms:
        if _pattern(term).search(text):
            leaks.append("staff name")
            break
    if EMAIL.search(text):
        leaks.append("email address")
    return leaks


def assert_clean(text: str, learner: Learner, staff_terms: list[str]) -> None:
    leaks = find_leaks(text, learner, staff_terms)
    if leaks:
        raise IdentifierLeak(", ".join(sorted(set(leaks))))


# --- Package -----------------------------------------------------------------------------


def _week(on: date, start: date | None) -> int | None:
    if start is None:
        return None
    return max(1, (on - start).days // 7 + 1)


def _age(birth: date, on: date) -> int:
    return on.year - birth.year - ((on.month, on.day) < (birth.month, birth.day))


def staff_names(db: Session, iep: Iep) -> list[str]:
    """Every user's name plus IEP team member names: all of them are scrubbed."""
    names = [u.name for u in db.scalars(select(User))]
    names += [m.get("name", "") for m in (iep.team_members or [])]
    for goal in iep.goals:
        if goal.responsible_staff:
            names += [part.split("(")[0] for part in re.split(r"[;,]", goal.responsible_staff)]
    return [n for n in names if n and n.strip()]


def build_package(db: Session, learner: Learner, today: date | None = None) -> EvidencePackage:
    iep = ilaw_alignment_service.active_iep(db, learner)
    if iep is None:
        raise conflict("no_active_iep", "The learner has no finalized IEP for this school year.")
    today = today or date.today()
    scrub = Scrubber(learner, staff_names(db, iep), get_settings().school_name)
    start = iep.start_date

    goals_out, goal_ids, goal_status = [], {}, {}
    goal_ref = {}
    for number, goal in enumerate(iep.goals, 1):
        gid = f"G{number}"
        goal_ref[goal.id] = gid
        goal_ids[gid] = goal.id
        gp = progress_service.goal_progress(db, goal, number, today)
        goal_status[gid] = gp.status.status
        pts = gp.points
        goals_out.append({
            "id": gid,
            "domain": goal.domain,
            "skill": goal.skill_name,
            "statement": scrub(goal.statement),
            "baseline": scrub(goal.baseline),
            "baseline_value": goal.baseline_value,
            "target_value": goal.target_value,
            "unit": goal.target_unit,
            "criterion": scrub(goal.criterion),
            "measurement": goal.measurement_method,
            "computed_status": gp.status.status,
            "latest_value": gp.status.latest,
            "expected_now_on_aim_line": gp.status.expected,
            "data_points": len(pts),
            "first_point": {"week": _week(pts[0].recorded_on, start), "value": pts[0].value} if pts else None,
            "last_point": {"week": _week(pts[-1].recorded_on, start), "value": pts[-1].value} if pts else None,
        })

    findings_out = [
        {"id": f"F{f.id}", "category": f.category, "domain": f.domain, "text": scrub(f.text)}
        for f in extraction_service.approved_findings_for_learner(db, learner.id)
    ]

    records = list(db.scalars(
        select(ProgressRecord).where(ProgressRecord.learner_id == learner.id, ProgressRecord.iep_id == iep.id)
        .order_by(ProgressRecord.recorded_on, ProgressRecord.id)
    ).unique())
    progress_out, observations_out, grades_out = [], [], []
    per_goal: dict[int, list] = {}
    for r in records:
        if r.evidence_type == "grade":
            grades_out.append({"id": f"R{r.id}", "subject": scrub(r.subject), "period": r.grading_period,
                               "value": r.value, "goal": goal_ref.get(r.iep_goal_id)})
        elif r.evidence_type == "observation":
            observations_out.append({"id": f"O{r.id}", "goal": goal_ref.get(r.iep_goal_id), "week": _week(r.recorded_on, start),
                                     "value": r.value, "unit": r.unit, "note": scrub(r.note)})
        else:
            per_goal.setdefault(r.iep_goal_id, []).append(r)
    for goal_id, items in per_goal.items():
        keep = items if len(items) <= MAX_POINTS_PER_GOAL else [items[0]] + items[-(MAX_POINTS_PER_GOAL - 1):]
        for r in keep:
            progress_out.append({"id": f"P{r.id}", "goal": goal_ref.get(goal_id), "type": r.evidence_type,
                                 "week": _week(r.recorded_on, start), "value": r.value, "out_of": r.out_of,
                                 "unit": r.unit, "note": scrub(r.note)})

    entries = list(db.scalars(
        select(IlawEntry).where(IlawEntry.learner_id == learner.id).order_by(IlawEntry.activity_date.desc())
    ).unique())
    activities_out, counted = [], {}
    for e in entries:
        linked = [goal_ref[a.iep_goal_id] for a in e.alignments if a.status == "confirmed" and a.iep_goal_id in goal_ref]
        if not linked or all(counted.get(g, 0) >= MAX_ACTIVITIES_PER_GOAL for g in linked):
            continue
        for g in linked:
            counted[g] = counted.get(g, 0) + 1
        activities_out.append({"id": f"A{e.id}", "goals": linked, "week": _week(e.activity_date, start),
                               "title": scrub(e.title), "summary": scrub(e.learner_response or e.description)})
    for goal in goals_out:
        goal["linked_activities"] = sum(1 for e in entries for a in e.alignments
                                        if a.status == "confirmed" and goal_ref.get(a.iep_goal_id) == goal["id"])

    package = {
        "learner": {"ref": "[LEARNER]", "grade": GRADE_NAMES.get(learner.grade_level, f"Grade {learner.grade_level}"),
                    "age_years": _age(learner.birth_date, iep.start_date or today)},
        "iep": {"school_year": iep.school_year, "version": iep.version_number,
                "length_weeks": _week(iep.end_date, start) if iep.end_date else None},
        "goals": goals_out,
        "findings": findings_out,
        "progress": progress_out,
        "activities": activities_out,
        "observations": observations_out,
        "grades": grades_out,
    }
    text = canonical(package)
    staff_terms = scrub.staff_terms
    try:
        assert_clean(text, learner, staff_terms)
    except IdentifierLeak as exc:  # fail closed: never return a package with identifiers
        raise APIError(500, "deidentification_failed",
                       f"The evidence could not be de-identified safely ({exc}). Nothing was sent.") from exc
    ids = [g["id"] for g in goals_out] + [i["id"] for key in ("findings", "progress", "activities", "observations", "grades") for i in package[key]]
    return EvidencePackage(
        package=package, ids=ids, hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        goal_ids=goal_ids, goal_status=goal_status, learner_terms=scrub.learner_terms,
        staff_terms=staff_terms, first_name=learner.first_name, iep_id=iep.id,
    )


def canonical(package: dict) -> str:
    return json.dumps(package, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def reidentify(text: str, first_name: str) -> str:
    return text.replace("[LEARNER]", first_name).replace("[STAFF]", "the teacher").replace("[SCHOOL]", "the school")
