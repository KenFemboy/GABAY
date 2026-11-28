"""Year-end evaluation API (Stage 12)."""

from collections.abc import Callable

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.permissions import require_assessment_writers, require_evaluation_finalizers, require_learner_readers
from app.db.session import get_db
from app.models.evaluation import Evaluation
from app.models.user import User
from app.schemas.evaluation import (
    EvaluationContent,
    EvaluationList,
    EvaluationRead,
    EvaluationSummary,
    GenerateBody,
    PreviewRead,
)
from app.services import evaluation_service, learner_service
from app.services.evaluation_ai import EvaluationModel, OpenAIEvaluationModel

router = APIRouter(prefix="/api", tags=["evaluations"])


def get_model_factory() -> Callable[[], EvaluationModel]:
    """FastAPI dependency; tests override it with a fake model."""
    return OpenAIEvaluationModel


def _visible(db: Session, evaluation_id: int, user: User) -> Evaluation:
    evaluation = evaluation_service.get_evaluation(db, evaluation_id)
    learner_service.get_visible_learner(db, evaluation.learner_id, user)
    return evaluation


def _read(evaluation: Evaluation, fallback_reason: str | None = None) -> EvaluationRead:
    return EvaluationRead.model_validate(evaluation).model_copy(update={"fallback_reason": fallback_reason})


@router.get("/learners/{learner_id}/evaluations", response_model=EvaluationList)
def list_evaluations(learner_id: int, db: Session = Depends(get_db), user: User = Depends(require_learner_readers)):
    learner = learner_service.get_visible_learner(db, learner_id, user)
    return EvaluationList(items=[EvaluationSummary.model_validate(e) for e in evaluation_service.list_for_learner(db, learner.id)])


@router.get("/learners/{learner_id}/evaluations/preview", response_model=PreviewRead)
def preview(learner_id: int, db: Session = Depends(get_db), user: User = Depends(require_assessment_writers)):
    learner = learner_service.get_visible_learner(db, learner_id, user)
    evidence = evaluation_service.preview(db, learner)
    state = evaluation_service.ai_state()
    return PreviewRead(
        ai_enabled=state["enabled"], ai_configured=state["configured"], evidence_hash=evidence.hash,
        evidence_count=len(evidence.ids), package=evidence.package, sent_to="OpenAI (only when you click Generate draft)",
    )


@router.post("/learners/{learner_id}/evaluations/generate", response_model=EvaluationRead, status_code=status.HTTP_201_CREATED)
def generate(
    learner_id: int,
    payload: GenerateBody,
    db: Session = Depends(get_db),
    user: User = Depends(require_assessment_writers),
    model_factory: Callable[[], EvaluationModel] = Depends(get_model_factory),
) -> EvaluationRead:
    learner = learner_service.get_visible_learner(db, learner_id, user)
    evaluation, fallback = evaluation_service.generate_draft(db, user, learner, model_factory, payload.evidence_hash)
    return _read(evaluation, fallback)


@router.post("/learners/{learner_id}/evaluations/manual", response_model=EvaluationRead, status_code=status.HTTP_201_CREATED)
def manual(learner_id: int, db: Session = Depends(get_db), user: User = Depends(require_assessment_writers)):
    learner = learner_service.get_visible_learner(db, learner_id, user)
    return _read(evaluation_service.create_manual(db, user, learner))


@router.get("/evaluations/{evaluation_id}", response_model=EvaluationRead)
def get_evaluation(evaluation_id: int, db: Session = Depends(get_db), user: User = Depends(require_learner_readers)):
    return _read(_visible(db, evaluation_id, user))


@router.patch("/evaluations/{evaluation_id}", response_model=EvaluationRead)
def update(evaluation_id: int, payload: EvaluationContent, db: Session = Depends(get_db), user: User = Depends(require_assessment_writers)):
    evaluation = _visible(db, evaluation_id, user)
    content = payload.model_dump(mode="json")
    return _read(evaluation_service.update(db, evaluation, content))


@router.post("/evaluations/{evaluation_id}/finalize", response_model=EvaluationRead)
def finalize(evaluation_id: int, db: Session = Depends(get_db), user: User = Depends(require_evaluation_finalizers)):
    evaluation = _visible(db, evaluation_id, user)
    return _read(evaluation_service.finalize(db, user, evaluation))


@router.delete("/evaluations/{evaluation_id}", status_code=status.HTTP_204_NO_CONTENT)
def discard(evaluation_id: int, db: Session = Depends(get_db), user: User = Depends(require_assessment_writers)):
    evaluation = _visible(db, evaluation_id, user)
    evaluation_service.discard(db, evaluation)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
