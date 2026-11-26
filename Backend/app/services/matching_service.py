"""Semantic goal matching (Stage 8).

Approved NEED findings of a learner are embedded with the same model as the
goal bank, and the closest active goals are found with ``vector_search``
(pgvector on PostgreSQL). Each run's ranked suggestions are saved with score,
rank and model version; staff then accept (optionally with edited wording),
reject, or add goals manually. Accepting records a goal usage, which locks
that goal version's wording in the goal bank.

The IEP stage must read a learner's chosen goals through
``selected_goals_for_learner``.
"""

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import APIError, conflict, not_found
from app.models.extraction import ExtractionFinding
from app.models.goal import Goal, GoalDomain, GoalStatus
from app.models.learner import Learner
from app.models.matching import (
    GoalRecommendation,
    MatchingRun,
    NeedEmbedding,
    RecommendationSource,
    RecommendationStatus,
)
from app.models.user import User
from app.services import embedding_service, extraction_service, goal_service
from app.services.embedding_service import Embedder, check_dims, vector_search
from app.services.extraction.schema import FindingCategory

# Bump TEXT_VERSION when need_text()/embedding_text() change, so saved
# recommendations show which text format produced them.
TEXT_VERSION = "text-v1"

SUGGESTED = RecommendationStatus.SUGGESTED.value
ACCEPTED = RecommendationStatus.ACCEPTED.value
REJECTED = RecommendationStatus.REJECTED.value

GRADE_BANDS = {
    "K": "K-3", "1": "K-3", "2": "K-3", "3": "K-3",
    "4": "4-6", "5": "4-6", "6": "4-6",
    "7": "7-10", "8": "7-10", "9": "7-10", "10": "7-10",
    "11": "11-12", "12": "11-12",
}


def model_version(model: str) -> str:
    return f"{model}|{TEXT_VERSION}"


def grade_band_for(learner: Learner) -> str | None:
    return GRADE_BANDS.get(learner.grade_level)  # NG (non-graded) -> no grade filter


def _now() -> datetime:
    return datetime.now(UTC)


# --- Needs and their embeddings -------------------------------------------------------


def approved_needs(db: Session, learner_id: int) -> list[ExtractionFinding]:
    """Approved NEED findings only (via the Stage 6 goal-matching gate)."""
    return [
        f
        for f in extraction_service.approved_findings_for_learner(db, learner_id)
        if f.category == FindingCategory.NEED.value
    ]


def _domain_names(db: Session) -> dict[str, str]:
    return {d.code: d.name for d in db.scalars(select(GoalDomain))}


def need_text(finding: ExtractionFinding, domain_names: dict[str, str]) -> str:
    """Same shape as goal texts ("Domain – skill: statement") so vectors are comparable."""
    name = domain_names.get(finding.domain or "")
    return f"{name} – {finding.text.strip()}" if name else finding.text.strip()


def ensure_need_embeddings(
    db: Session, findings: list[ExtractionFinding], embedder: Embedder
) -> dict[int, np.ndarray]:
    """Return {finding_id: vector}, embedding only findings without an up-to-date vector."""
    names = _domain_names(db)
    texts = {f.id: need_text(f, names) for f in findings}
    hashes = {fid: hashlib.sha256(t.encode("utf-8")).hexdigest() for fid, t in texts.items()}
    rows = {
        r.finding_id: r
        for r in db.scalars(
            select(NeedEmbedding).where(
                NeedEmbedding.model == embedder.model, NeedEmbedding.finding_id.in_(list(texts) or [-1])
            )
        )
    }
    todo = [fid for fid in texts if fid not in rows or rows[fid].text_hash != hashes[fid]]
    for start in range(0, len(todo), embedding_service.BATCH_SIZE):
        batch = todo[start:start + embedding_service.BATCH_SIZE]
        vectors = check_dims(embedder.embed([texts[fid] for fid in batch]))
        for fid, vector in zip(batch, vectors, strict=True):
            if fid in rows:
                rows[fid].text_hash = hashes[fid]
                rows[fid].embedding = vector
            else:
                rows[fid] = NeedEmbedding(
                    finding_id=fid, model=embedder.model, text_hash=hashes[fid], embedding=vector
                )
                db.add(rows[fid])
    db.flush()
    return {fid: np.asarray(rows[fid].embedding, dtype=np.float32) for fid in texts}


# --- Running matching -------------------------------------------------------------------


@dataclass
class MatchOptions:
    top_k: int
    min_score: float
    same_domain: bool = True
    use_grade_band: bool = True

    @classmethod
    def defaults(cls) -> "MatchOptions":
        settings = get_settings()
        return cls(top_k=settings.match_top_k, min_score=settings.match_min_score)


def _previous_decisions(db: Session, learner_id: int) -> dict[tuple[int, int], GoalRecommendation]:
    """Latest decided recommendation per (finding, goal version) for this learner."""
    decided: dict[tuple[int, int], GoalRecommendation] = {}
    rows = db.scalars(
        select(GoalRecommendation)
        .where(
            GoalRecommendation.learner_id == learner_id,
            GoalRecommendation.status != SUGGESTED,
            GoalRecommendation.finding_id.is_not(None),
        )
        .order_by(GoalRecommendation.decided_at, GoalRecommendation.id)
    ).unique()
    for rec in rows:
        decided[(rec.finding_id, rec.goal_version_id)] = rec
    return decided


def run_matching(
    db: Session, user: User, learner: Learner, options: MatchOptions, embedder: Embedder
) -> MatchingRun:
    needs = approved_needs(db, learner.id)
    if not needs:
        raise conflict(
            "no_approved_needs",
            "This learner has no approved needs yet. Approve an assessment analysis first.",
        )
    # Make sure goal vectors exist for every active goal before searching.
    embedding_service.reindex_if_needed(db, embedder)
    vectors = ensure_need_embeddings(db, needs, embedder)

    band = grade_band_for(learner) if options.use_grade_band else None
    version = model_version(embedder.model)
    run = MatchingRun(
        learner_id=learner.id,
        model=embedder.model,
        model_version=version,
        top_k=options.top_k,
        min_score=options.min_score,
        same_domain=options.same_domain,
        grade_band=band,
        need_count=len(needs),
        created_by=user.id,
    )
    db.add(run)
    db.flush()

    previous = _previous_decisions(db, learner.id)
    for need in needs:
        hits = vector_search(
            db,
            vectors[need.id],
            model=embedder.model,
            k=options.top_k,
            min_score=options.min_score,
            domain_code=need.domain if options.same_domain and need.domain else None,
            grade_band=band,
        )
        for rank, hit in enumerate(hits, 1):
            rec = GoalRecommendation(
                run_id=run.id,
                learner_id=learner.id,
                finding_id=need.id,
                goal_id=hit.goal.id,
                goal_version_id=hit.version.id,
                source=RecommendationSource.MATCHED.value,
                score=round(hit.score, 6),
                rank=rank,
                model_version=version,
                status=SUGGESTED,
            )
            earlier = previous.get((need.id, hit.version.id))
            if earlier is not None:  # carry the earlier decision over
                rec.status = earlier.status
                rec.edited_statement = earlier.edited_statement
                rec.edited_target_value = earlier.edited_target_value
                rec.edited_criterion = earlier.edited_criterion
                rec.reject_reason = earlier.reject_reason
                rec.decided_by = earlier.decided_by
                rec.decided_at = earlier.decided_at
            db.add(rec)
    db.commit()
    db.refresh(run)
    return run


# --- Reading ------------------------------------------------------------------------------


def latest_run(db: Session, learner_id: int) -> MatchingRun | None:
    return db.scalar(
        select(MatchingRun)
        .where(MatchingRun.learner_id == learner_id)
        .order_by(MatchingRun.created_at.desc(), MatchingRun.id.desc())
        .limit(1)
    )


def list_runs(db: Session, learner_id: int) -> list[MatchingRun]:
    return list(
        db.scalars(
            select(MatchingRun)
            .where(MatchingRun.learner_id == learner_id)
            .order_by(MatchingRun.created_at.desc(), MatchingRun.id.desc())
        ).unique()
    )


def get_run(db: Session, run_id: int) -> MatchingRun:
    run = db.get(MatchingRun, run_id)
    if run is None:
        raise not_found("Matching run not found.")
    return run


def manual_recommendations(db: Session, learner_id: int) -> list[GoalRecommendation]:
    return list(
        db.scalars(
            select(GoalRecommendation)
            .where(
                GoalRecommendation.learner_id == learner_id,
                GoalRecommendation.source == RecommendationSource.MANUAL.value,
            )
            .order_by(GoalRecommendation.id)
        ).unique()
    )


def selected_goals_for_learner(db: Session, learner_id: int) -> list[GoalRecommendation]:
    """The learner's chosen goals - the input for the IEP stage.

    = accepted recommendations of the LATEST run (earlier decisions are carried
    into every new run, so the latest run is the current state) + accepted
    manual additions; one per goal version.
    """
    chosen: dict[int, GoalRecommendation] = {}
    run = latest_run(db, learner_id)
    if run is not None:
        for rec in run.recommendations:
            if rec.status == ACCEPTED:
                chosen.setdefault(rec.goal_version_id, rec)
    for rec in manual_recommendations(db, learner_id):
        if rec.status == ACCEPTED:
            chosen.setdefault(rec.goal_version_id, rec)
    return sorted(chosen.values(), key=lambda r: (r.goal.code, r.id))


# --- Decisions -------------------------------------------------------------------------------


def get_recommendation(db: Session, rec_id: int) -> GoalRecommendation:
    rec = db.get(GoalRecommendation, rec_id)
    if rec is None:
        raise not_found("Recommendation not found.")
    return rec


def _apply_edits(rec: GoalRecommendation, edits: dict) -> None:
    for key in ("edited_statement", "edited_target_value", "edited_criterion"):
        if key in edits:
            value = edits[key]
            base = {
                "edited_statement": rec.goal_version.statement,
                "edited_target_value": rec.goal_version.target_value,
                "edited_criterion": rec.goal_version.criterion,
            }[key]
            # Store only real changes; identical wording means "use the bank's version".
            setattr(rec, key, None if value == base else value)


def accept(db: Session, user: User, rec: GoalRecommendation, edits: dict) -> GoalRecommendation:
    _apply_edits(rec, edits)
    rec.status = ACCEPTED
    rec.reject_reason = None
    rec.decided_by = user.id
    rec.decided_at = _now()
    goal_service.record_goal_usage(db, rec.goal_version_id, "goal_recommendation", rec.id)
    db.commit()
    db.refresh(rec)
    return rec


def edit(db: Session, user: User, rec: GoalRecommendation, edits: dict) -> GoalRecommendation:
    if rec.status != ACCEPTED:
        raise conflict("not_accepted", "Only accepted goals can be edited. Accept it first.")
    _apply_edits(rec, edits)
    rec.decided_by = user.id
    rec.decided_at = _now()
    db.commit()
    db.refresh(rec)
    return rec


def reject(db: Session, user: User, rec: GoalRecommendation, reason: str | None) -> GoalRecommendation:
    if rec.source == RecommendationSource.MANUAL.value:
        raise conflict("manual_goal", "Remove a manually added goal instead of rejecting it.")
    rec.status = REJECTED
    rec.reject_reason = reason
    rec.decided_by = user.id
    rec.decided_at = _now()
    db.commit()
    db.refresh(rec)
    return rec


def reset(db: Session, rec: GoalRecommendation) -> GoalRecommendation:
    """Back to 'suggested'. A recorded goal usage stays (the version remains locked)."""
    if rec.source == RecommendationSource.MANUAL.value:
        raise conflict("manual_goal", "Remove a manually added goal instead.")
    rec.status = SUGGESTED
    rec.reject_reason = None
    rec.edited_statement = rec.edited_target_value = rec.edited_criterion = None
    rec.decided_by = None
    rec.decided_at = None
    db.commit()
    db.refresh(rec)
    return rec


def remove_manual(db: Session, rec: GoalRecommendation) -> None:
    if rec.source != RecommendationSource.MANUAL.value:
        raise conflict("not_manual", "Only manually added goals can be removed. Reject suggestions instead.")
    db.delete(rec)
    db.commit()


def add_manual(
    db: Session, user: User, learner: Learner, goal_id: int, finding_id: int | None, edits: dict
) -> GoalRecommendation:
    goal = db.get(Goal, goal_id)
    if goal is None or goal.status != GoalStatus.ACTIVE.value:
        raise APIError(422, "invalid_goal", "Choose an active goal from the goal bank.")
    if finding_id is not None and finding_id not in {f.id for f in approved_needs(db, learner.id)}:
        raise APIError(422, "invalid_finding", "The need must be one of this learner's approved needs.")
    if any(r.goal_version_id == goal.current_version_id for r in selected_goals_for_learner(db, learner.id)):
        raise conflict("already_selected", "This goal is already selected for the learner.")
    rec = GoalRecommendation(
        run_id=None,
        learner_id=learner.id,
        finding_id=finding_id,
        goal_id=goal.id,
        goal_version_id=goal.current_version_id,
        source=RecommendationSource.MANUAL.value,
        status=SUGGESTED,
    )
    db.add(rec)
    db.flush()
    db.refresh(rec)
    return accept(db, user, rec, edits)
