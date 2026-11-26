"""Semantic goal matching API (Stage 8)."""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.permissions import require_assessment_writers, require_learner_readers
from app.db.session import get_db
from app.models.matching import GoalRecommendation, MatchingRun
from app.models.user import User
from app.schemas.matching import (
    GoalEdits,
    ManualAdd,
    NeedRead,
    RecommendationRead,
    RecommendationsView,
    RejectBody,
    RunDetail,
    RunList,
    RunOptions,
    RunRead,
    SelectedGoals,
)
from app.services import learner_service, matching_service
from app.services.embedding_service import Embedder, EmbeddingUnavailable, embeddings_unavailable, get_embedder
from app.services.matching_service import MatchOptions

router = APIRouter(prefix="/api", tags=["matching"])


def rec_read(rec: GoalRecommendation) -> RecommendationRead:
    return RecommendationRead.model_validate(
        {
            **{k: getattr(rec, k) for k in RecommendationRead.model_fields if k not in ("goal_code", "goal_version")},
            "goal_code": rec.goal.code,
            "goal_version": rec.goal_version,
        }
    )


def run_detail(db: Session, run: MatchingRun) -> RunDetail:
    by_finding: dict[int, list[GoalRecommendation]] = {}
    for rec in run.recommendations:
        by_finding.setdefault(rec.finding_id, []).append(rec)
    needs = []
    for need in matching_service.approved_needs(db, run.learner_id):
        needs.append(
            NeedRead(
                id=need.id,
                text=need.text,
                domain=need.domain,
                assessment_id=need.version.assessment_id,
                version_id=need.version_id,
                suggestions=[rec_read(r) for r in sorted(by_finding.get(need.id, []), key=lambda r: r.rank or 0)],
            )
        )
    return RunDetail(**RunRead.model_validate(run).model_dump(), needs=needs)


def _visible_rec(db: Session, rec_id: int, user: User) -> GoalRecommendation:
    rec = matching_service.get_recommendation(db, rec_id)
    learner_service.get_visible_learner(db, rec.learner_id, user)
    return rec


@router.post(
    "/learners/{learner_id}/matching-runs", response_model=RunDetail, status_code=status.HTTP_201_CREATED
)
def run_matching(
    learner_id: int,
    payload: RunOptions,
    db: Session = Depends(get_db),
    user: User = Depends(require_assessment_writers),
    embedder: Embedder = Depends(get_embedder),
) -> RunDetail:
    learner = learner_service.get_visible_learner(db, learner_id, user)
    defaults = MatchOptions.defaults()
    options = MatchOptions(
        top_k=payload.top_k or defaults.top_k,
        min_score=payload.min_score if payload.min_score is not None else defaults.min_score,
        same_domain=payload.same_domain,
        use_grade_band=payload.use_grade_band,
    )
    try:
        run = matching_service.run_matching(db, user, learner, options, embedder)
    except EmbeddingUnavailable as exc:
        db.rollback()
        raise embeddings_unavailable(exc) from exc
    return run_detail(db, run)


@router.get("/learners/{learner_id}/matching-runs", response_model=RunList)
def list_runs(learner_id: int, db: Session = Depends(get_db), user: User = Depends(require_learner_readers)):
    learner = learner_service.get_visible_learner(db, learner_id, user)
    return RunList(items=[RunRead.model_validate(r) for r in matching_service.list_runs(db, learner.id)])


@router.get("/matching-runs/{run_id}", response_model=RunDetail)
def get_run(run_id: int, db: Session = Depends(get_db), user: User = Depends(require_learner_readers)):
    run = matching_service.get_run(db, run_id)
    learner_service.get_visible_learner(db, run.learner_id, user)
    return run_detail(db, run)


@router.get("/learners/{learner_id}/recommendations/latest", response_model=RecommendationsView)
def latest_recommendations(
    learner_id: int, db: Session = Depends(get_db), user: User = Depends(require_learner_readers)
) -> RecommendationsView:
    learner = learner_service.get_visible_learner(db, learner_id, user)
    run = matching_service.latest_run(db, learner.id)
    return RecommendationsView(
        run=run_detail(db, run) if run else None,
        manual=[rec_read(r) for r in matching_service.manual_recommendations(db, learner.id)],
        selected=[rec_read(r) for r in matching_service.selected_goals_for_learner(db, learner.id)],
        approved_need_count=len(matching_service.approved_needs(db, learner.id)),
    )


@router.get("/learners/{learner_id}/selected-goals", response_model=SelectedGoals)
def selected_goals(learner_id: int, db: Session = Depends(get_db), user: User = Depends(require_learner_readers)):
    learner = learner_service.get_visible_learner(db, learner_id, user)
    return SelectedGoals(items=[rec_read(r) for r in matching_service.selected_goals_for_learner(db, learner.id)])


@router.post("/recommendations/{rec_id}/accept", response_model=RecommendationRead)
def accept(rec_id: int, payload: GoalEdits, db: Session = Depends(get_db), user: User = Depends(require_assessment_writers)):
    rec = _visible_rec(db, rec_id, user)
    return rec_read(matching_service.accept(db, user, rec, payload.model_dump(exclude_unset=True)))


@router.patch("/recommendations/{rec_id}", response_model=RecommendationRead)
def edit(rec_id: int, payload: GoalEdits, db: Session = Depends(get_db), user: User = Depends(require_assessment_writers)):
    rec = _visible_rec(db, rec_id, user)
    return rec_read(matching_service.edit(db, user, rec, payload.model_dump(exclude_unset=True)))


@router.post("/recommendations/{rec_id}/reject", response_model=RecommendationRead)
def reject(rec_id: int, payload: RejectBody, db: Session = Depends(get_db), user: User = Depends(require_assessment_writers)):
    rec = _visible_rec(db, rec_id, user)
    return rec_read(matching_service.reject(db, user, rec, payload.reason))


@router.post("/recommendations/{rec_id}/reset", response_model=RecommendationRead)
def reset(rec_id: int, db: Session = Depends(get_db), user: User = Depends(require_assessment_writers)):
    rec = _visible_rec(db, rec_id, user)
    return rec_read(matching_service.reset(db, rec))


@router.post(
    "/learners/{learner_id}/recommendations",
    response_model=RecommendationRead,
    status_code=status.HTTP_201_CREATED,
)
def add_manual(
    learner_id: int, payload: ManualAdd, db: Session = Depends(get_db), user: User = Depends(require_assessment_writers)
):
    learner = learner_service.get_visible_learner(db, learner_id, user)
    edits = payload.model_dump(exclude_unset=True, exclude={"goal_id", "finding_id"})
    return rec_read(matching_service.add_manual(db, user, learner, payload.goal_id, payload.finding_id, edits))


@router.delete("/recommendations/{rec_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_manual(rec_id: int, db: Session = Depends(get_db), user: User = Depends(require_assessment_writers)):
    rec = _visible_rec(db, rec_id, user)
    matching_service.remove_manual(db, rec)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
