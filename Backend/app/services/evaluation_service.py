"""Year-end evaluations (Stage 12): preview, AI draft with manual fallback, edit, finalize.

Rules:
* One open draft and at most one finalized evaluation per learner + school year.
* AI drafting needs EVALUATION_AI_ENABLED plus OPENAI_API_KEY/OPENAI_MODEL, and a
  staff member who has previewed the exact de-identified package (its hash is
  re-checked before anything is sent).
* Any AI failure saves a MANUAL draft prefilled from the evidence instead.
* Finalized evaluations are read-only.
"""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import APIError, conflict, not_found
from app.models.evaluation import Evaluation, EvaluationSource, EvaluationStatus, GoalRating
from app.models.learner import Learner
from app.models.user import User
from app.services import learner_service
from app.services.evaluation_ai import (
    AiInvalidResponse,
    AiUnavailable,
    EvaluationModel,
    draft_to_json,
    generate,
)
from app.services.evaluation_evidence import EvidencePackage, build_package, reidentify

DRAFT = EvaluationStatus.DRAFT.value
FINALIZED = EvaluationStatus.FINALIZED.value
UNIT = {"percent": "%", "trials": " trials", "count": "", "minutes": " minutes", "wpm": " words per minute", "level": ""}
STATUS_TO_RATING = {
    "met": GoalRating.MET.value,
    "on_track": GoalRating.PROGRESSING.value,
    "below_aim": GoalRating.LIMITED_PROGRESS.value,
    "no_recent_data": GoalRating.LIMITED_PROGRESS.value,
}


def _now() -> datetime:
    return datetime.now(UTC)


def ai_state() -> dict:
    settings = get_settings()
    return {"enabled": settings.evaluation_ai_enabled, "configured": settings.evaluation_ai_configured}


# --- Lookups -------------------------------------------------------------------------------


def get_evaluation(db: Session, evaluation_id: int) -> Evaluation:
    evaluation = db.get(Evaluation, evaluation_id)
    if evaluation is None:
        raise not_found("Evaluation not found.")
    return evaluation


def list_for_learner(db: Session, learner_id: int) -> list[Evaluation]:
    return list(db.scalars(
        select(Evaluation).where(Evaluation.learner_id == learner_id)
        .order_by(Evaluation.school_year.desc(), Evaluation.created_at.desc(), Evaluation.id.desc())
    ).unique())


def _require_slot(db: Session, learner: Learner) -> None:
    rows = db.scalars(select(Evaluation.status).where(
        Evaluation.learner_id == learner.id, Evaluation.school_year == learner.school_year)).all()
    if FINALIZED in rows:
        raise conflict("evaluation_exists", "A finalized evaluation already exists for this school year.")
    if DRAFT in rows:
        raise conflict("draft_exists", "A draft evaluation already exists. Open it, or discard it first.")


def _require_draft(evaluation: Evaluation) -> None:
    if evaluation.status != DRAFT:
        raise conflict("evaluation_read_only", "This evaluation is finalized and cannot be changed.")


# --- Manual skeleton ---------------------------------------------------------------------------


def _fmt(value, unit) -> str:
    if value is None:
        return "—"
    v = int(value) if float(value).is_integer() else round(value, 1)
    return f"{v}{UNIT.get(unit or '', '')}"


def manual_content(evidence: EvidencePackage) -> dict:
    """Prefilled skeleton from the evidence numbers. Staff complete the wording."""
    goals = []
    for g in evidence.package["goals"]:
        status = g["computed_status"]
        if g["data_points"]:
            first, last = g["first_point"], g["last_point"]
            narrative = (
                f"Baseline: {g['baseline'] or _fmt(g['baseline_value'], g['unit'])}. "
                f"{g['data_points']} data point(s) were recorded, from {_fmt(first['value'], g['unit'])} "
                f"(week {first['week']}) to {_fmt(last['value'], g['unit'])} (week {last['week']}). "
                f"Target: {_fmt(g['target_value'], g['unit'])}{' ' + g['criterion'] if g['criterion'] else ''}. "
            )
        else:
            narrative = "No progress data was recorded for this goal. "
        if g.get("linked_activities"):
            narrative += f"{g['linked_activities']} logged learning activit{'y' if g['linked_activities'] == 1 else 'ies'} worked on this goal. "
        narrative += "[Describe the learner's progress here.]"
        goals.append({
            "iep_goal_id": evidence.goal_ids[g["id"]],
            "rating": STATUS_TO_RATING.get(status, GoalRating.INSUFFICIENT_EVIDENCE.value),
            "narrative": reidentify(narrative, evidence.first_name),
            "evidence_ids": [g["id"]],
        })
    return {
        "summary": "",
        "goals": goals,
        "strengths": [
            {"text": reidentify(f["text"], evidence.first_name), "evidence_ids": [f["id"]]}
            for f in evidence.package["findings"] if f["category"] == "strength"
        ][:5],
        "recommendations": [],
    }


def _save(db: Session, user: User, learner: Learner, evidence: EvidencePackage, **fields) -> Evaluation:
    evaluation = Evaluation(
        learner_id=learner.id,
        iep_id=evidence.iep_id,
        school_year=learner.school_year,
        status=DRAFT,
        evidence_ids=evidence.ids,
        evidence_hash=evidence.hash,
        evidence_snapshot=evidence.package,
        created_by=user.id,
        **fields,
    )
    db.add(evaluation)
    db.commit()
    db.refresh(evaluation)
    return evaluation


# --- Create -------------------------------------------------------------------------------------


def preview(db: Session, learner: Learner) -> EvidencePackage:
    return build_package(db, learner)


def create_manual(db: Session, user: User, learner: Learner, *, error: str | None = None,
                  evidence: EvidencePackage | None = None) -> Evaluation:
    if error is None:
        _require_slot(db, learner)
    evidence = evidence or build_package(db, learner)
    return _save(db, user, learner, evidence, source=EvaluationSource.MANUAL.value,
                 content=manual_content(evidence), generation_error=error)


def generate_draft(db: Session, user: User, learner: Learner, model_factory, evidence_hash: str) -> tuple[Evaluation, str | None]:
    """Returns (evaluation, fallback_reason). fallback_reason is set when a manual draft was saved instead."""
    state = ai_state()
    if not state["enabled"] or not state["configured"]:
        raise conflict("ai_disabled", "AI drafting is not enabled. Write the evaluation manually instead.")
    _require_slot(db, learner)
    evidence = build_package(db, learner)
    if evidence.hash != evidence_hash:
        raise conflict("evidence_changed", "The evidence changed after the preview. Review the preview again.")

    try:
        model: EvaluationModel = model_factory()
        result = generate(evidence, learner, model)
    except (AiUnavailable, AiInvalidResponse) as exc:
        reason = str(exc)[:480] or exc.__class__.__name__
        if isinstance(exc, AiInvalidResponse):
            reason = "The AI draft did not pass the checks: " + reason
        evaluation = create_manual(db, user, learner, error=reason, evidence=evidence)
        return evaluation, reason

    d = result.draft
    by_ref = evidence.goal_ids
    content = {
        "summary": reidentify(d.summary, evidence.first_name),
        "summary_evidence_ids": d.summary_evidence_ids,
        "goals": [
            {"iep_goal_id": by_ref[g.goal_id], "rating": g.rating,
             "narrative": reidentify(g.narrative, evidence.first_name), "evidence_ids": g.evidence_ids}
            for g in sorted(d.goals, key=lambda g: list(by_ref).index(g.goal_id))
        ],
        "strengths": [{"text": reidentify(s.text, evidence.first_name), "evidence_ids": s.evidence_ids} for s in d.strengths],
        "recommendations": [{"text": reidentify(r.text, evidence.first_name), "evidence_ids": r.evidence_ids} for r in d.recommendations],
    }
    evaluation = _save(
        db, user, learner, evidence, source=EvaluationSource.AI.value, model=result.model,
        prompt_version=result.prompt_version, raw_response=result.raw_text or draft_to_json(d),
        validation_warnings=result.warnings, content=content,
    )
    return evaluation, None


# --- Edit / finalize ------------------------------------------------------------------------------


def update(db: Session, evaluation: Evaluation, content: dict) -> Evaluation:
    _require_draft(evaluation)
    snapshot_ids = set(evaluation.evidence_ids or [])
    goal_ids = {g["iep_goal_id"] for g in evaluation.content.get("goals", [])}
    details = []
    for i, g in enumerate(content.get("goals", [])):
        if g["iep_goal_id"] not in goal_ids:
            details.append({"field": f"goals.{i}.iep_goal_id", "message": "This goal is not part of the evaluation."})
    for section in ("goals", "strengths", "recommendations"):
        for i, item in enumerate(content.get(section, [])):
            unknown = [e for e in item.get("evidence_ids", []) if e not in snapshot_ids]
            if unknown:
                details.append({"field": f"{section}.{i}.evidence_ids", "message": f"Unknown evidence IDs: {', '.join(unknown)}."})
    if sorted(g["iep_goal_id"] for g in content.get("goals", [])) != sorted(goal_ids):
        details.append({"field": "goals", "message": "Every goal of the evaluation must be kept exactly once."})
    if details:
        raise APIError(422, "invalid_evaluation", "Check the highlighted parts.", details=details)
    evaluation.content = {**content, "summary_evidence_ids": evaluation.content.get("summary_evidence_ids", [])}
    db.commit()
    db.refresh(evaluation)
    return evaluation


def finalize(db: Session, user: User, evaluation: Evaluation) -> Evaluation:
    _require_draft(evaluation)
    content = evaluation.content or {}
    details = []
    if len((content.get("summary") or "").strip()) < 20:
        details.append({"field": "summary", "message": "Write the overall summary (at least 20 characters)."})
    for i, g in enumerate(content.get("goals", [])):
        narrative = (g.get("narrative") or "").strip()
        if len(narrative) < 20 or "[Describe" in narrative:
            details.append({"field": f"goals.{i}.narrative", "message": f"Complete the narrative for goal {i + 1}."})
        if g.get("rating") not in {r.value for r in GoalRating}:
            details.append({"field": f"goals.{i}.rating", "message": f"Choose a rating for goal {i + 1}."})
    if details:
        raise APIError(422, "evaluation_incomplete", "The evaluation is not complete yet.", details=details)
    evaluation.status = FINALIZED
    evaluation.finalized_by = user.id
    evaluation.finalized_at = _now()
    db.commit()
    db.refresh(evaluation)
    return evaluation


def discard(db: Session, evaluation: Evaluation) -> None:
    _require_draft(evaluation)
    db.delete(evaluation)
    db.commit()


def summary_for_learner(db: Session, learner_id: int) -> tuple[int, str | None, datetime | None]:
    count = db.scalar(select(func.count(Evaluation.id)).where(Evaluation.learner_id == learner_id)) or 0
    latest = db.scalar(select(Evaluation).where(Evaluation.learner_id == learner_id).order_by(Evaluation.updated_at.desc()).limit(1))
    return count, (latest.status if latest else None), (latest.updated_at if latest else None)


learner_service.MODULE_COUNTERS["evaluations"] = summary_for_learner

