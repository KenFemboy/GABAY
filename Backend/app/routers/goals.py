"""Goal bank API (Stage 7). Only the SNED Coordinator manages goals and taxonomy."""

from dataclasses import asdict

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import require_goal_managers, require_learner_readers
from app.db.session import get_db
from app.models.goal import Goal, GoalEmbedding, GoalStatus, GradeBand, MeasurementMethod
from app.models.user import Role, User
from app.schemas.goal import (
    DomainCreate,
    DomainRead,
    DomainUpdate,
    GoalCreate,
    GoalDetail,
    GoalList,
    GoalRead,
    GoalUpdate,
    GoalUpdateResult,
    IndexStatusRead,
    ReindexResult,
    SearchHitRead,
    SearchResult,
    SkillCreate,
    SkillRead,
    SkillUpdate,
    TaxonomyRead,
)
from app.services import embedding_service, goal_service
from app.services.embedding_service import Embedder, EmbeddingUnavailable, get_embedder

router = APIRouter(prefix="/api", tags=["goals"])


def _is_manager(user: User) -> bool:
    return user.role == Role.SNED_COORDINATOR.value


def _goal_read(goal: Goal) -> GoalRead:
    return GoalRead(**GoalRead.model_validate(goal).model_dump(exclude={"in_use"}),
                    in_use=goal_service.is_used(goal.current_version))


def _goal_detail(db: Session, goal: Goal, model: str) -> GoalDetail:
    settings_model = model
    row = db.scalar(
        select(GoalEmbedding).where(
            GoalEmbedding.goal_version_id == goal.current_version_id, GoalEmbedding.model == settings_model
        )
    )
    indexed = row is not None and row.text_hash == embedding_service.text_hash(
        embedding_service.embedding_text(goal.current_version)
    )
    base = GoalDetail.model_validate(goal).model_dump(exclude={"in_use", "indexed"})
    return GoalDetail(**base, in_use=goal_service.is_used(goal.current_version), indexed=indexed)


# --- Taxonomy ------------------------------------------------------------------


@router.get("/goal-taxonomy", response_model=TaxonomyRead)
def get_taxonomy(db: Session = Depends(get_db), user: User = Depends(require_learner_readers)) -> TaxonomyRead:
    manager = _is_manager(user)
    domains = goal_service.list_domains(db, include_inactive=manager)
    out = []
    for d in domains:
        data = DomainRead.model_validate(d)
        if not manager:
            data.skills = [s for s in data.skills if s.is_active]
        out.append(data)
    return TaxonomyRead(domains=out)


@router.post("/goal-taxonomy/domains", response_model=DomainRead, status_code=status.HTTP_201_CREATED)
def create_domain(payload: DomainCreate, db: Session = Depends(get_db), _: User = Depends(require_goal_managers)):
    return goal_service.create_domain(db, payload.model_dump())


@router.patch("/goal-taxonomy/domains/{domain_id}", response_model=DomainRead)
def update_domain(
    domain_id: int, payload: DomainUpdate, db: Session = Depends(get_db), _: User = Depends(require_goal_managers)
):
    domain = goal_service.get_domain(db, domain_id)
    changes = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None or k == "description"}
    return goal_service.update_domain(db, domain, changes)


@router.post("/goal-taxonomy/skills", response_model=SkillRead, status_code=status.HTTP_201_CREATED)
def create_skill(payload: SkillCreate, db: Session = Depends(get_db), _: User = Depends(require_goal_managers)):
    return goal_service.create_skill(db, payload.model_dump())


@router.patch("/goal-taxonomy/skills/{skill_id}", response_model=SkillRead)
def update_skill(
    skill_id: int, payload: SkillUpdate, db: Session = Depends(get_db), _: User = Depends(require_goal_managers)
):
    skill = goal_service.get_skill(db, skill_id)
    changes = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None or k == "description"}
    return goal_service.update_skill(db, skill, changes)


# --- Index / search (declared before /goals/{goal_id}) ---------------------------


@router.get("/goals/index-status", response_model=IndexStatusRead)
def get_index_status(
    db: Session = Depends(get_db),
    _: User = Depends(require_goal_managers),
    embedder: Embedder = Depends(get_embedder),
) -> IndexStatusRead:
    return IndexStatusRead(**asdict(embedding_service.index_status(db, embedder.model)))


@router.post("/goals/reindex", response_model=ReindexResult)
def reindex_goals(
    db: Session = Depends(get_db),
    _: User = Depends(require_goal_managers),
    embedder: Embedder = Depends(get_embedder),
) -> ReindexResult:
    try:
        result = embedding_service.reindex(db, embedder)
    except EmbeddingUnavailable as exc:
        db.rollback()
        raise embedding_service.embeddings_unavailable(exc) from exc
    status_ = IndexStatusRead(**asdict(embedding_service.index_status(db, embedder.model)))
    return ReindexResult(**result, status=status_)


@router.get("/goals/search", response_model=SearchResult)
def search_goals(
    q: str = Query(min_length=3, max_length=500),
    k: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
    _: User = Depends(require_learner_readers),
    embedder: Embedder = Depends(get_embedder),
) -> SearchResult:
    try:
        hits = embedding_service.search(db, q, embedder, k)
    except EmbeddingUnavailable as exc:
        raise embedding_service.embeddings_unavailable(exc) from exc
    return SearchResult(items=[SearchHitRead(goal=_goal_read(h.goal), score=round(h.score, 4)) for h in hits])


# --- Goals -------------------------------------------------------------------------


@router.get("/goals", response_model=GoalList)
def list_goals(
    status_: GoalStatus | None = Query(default=None, alias="status"),
    domain: int | None = None,
    skill: int | None = None,
    grade_band: GradeBand | None = None,
    method: MeasurementMethod | None = None,
    q: str | None = Query(default=None, max_length=100),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(require_learner_readers),
) -> GoalList:
    items, total = goal_service.list_goals(
        db,
        manager=_is_manager(user),
        status=status_.value if status_ else None,
        domain_id=domain,
        skill_id=skill,
        grade_band=grade_band.value if grade_band else None,
        method=method.value if method else None,
        q=q,
        offset=offset,
        limit=limit,
    )
    return GoalList(items=[_goal_read(g) for g in items], total=total)


@router.get("/goals/{goal_id}", response_model=GoalDetail)
def get_goal(
    goal_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_learner_readers),
    embedder: Embedder = Depends(get_embedder),
):
    return _goal_detail(db, goal_service.get_goal(db, goal_id, manager=_is_manager(user)), embedder.model)


@router.post("/goals", response_model=GoalDetail, status_code=status.HTTP_201_CREATED)
def create_goal(
    payload: GoalCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_goal_managers),
    embedder: Embedder = Depends(get_embedder),
):
    data = payload.model_dump(exclude={"code"})
    data = {k: (v.value if hasattr(v, "value") else v) for k, v in data.items()}
    goal = goal_service.create_goal(db, user, data, code=payload.code)
    return _goal_detail(db, goal, embedder.model)


@router.patch("/goals/{goal_id}", response_model=GoalUpdateResult)
def update_goal(
    goal_id: int,
    payload: GoalUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_goal_managers),
    embedder: Embedder = Depends(get_embedder),
):
    goal = goal_service.get_goal(db, goal_id, manager=True)
    changes = {
        k: (v.value if hasattr(v, "value") else v)
        for k, v in payload.model_dump(exclude_unset=True).items()
        if v is not None or k in ("criterion", "change_note")
    }
    goal, new_version = goal_service.update_goal(db, user, goal, changes)
    return GoalUpdateResult(goal=_goal_detail(db, goal, embedder.model), new_version=new_version)


@router.post("/goals/{goal_id}/activate", response_model=GoalDetail)
def activate_goal(
    goal_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_goal_managers),
    embedder: Embedder = Depends(get_embedder),
):
    goal = goal_service.get_goal(db, goal_id, manager=True)
    return _goal_detail(db, goal_service.activate(db, goal), embedder.model)


@router.post("/goals/{goal_id}/archive", response_model=GoalDetail)
def archive_goal(
    goal_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_goal_managers),
    embedder: Embedder = Depends(get_embedder),
):
    goal = goal_service.get_goal(db, goal_id, manager=True)
    return _goal_detail(db, goal_service.archive(db, goal), embedder.model)


@router.delete("/goals/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_goal(goal_id: int, db: Session = Depends(get_db), _: User = Depends(require_goal_managers)) -> Response:
    goal_service.delete_goal(db, goal_service.get_goal(db, goal_id, manager=True))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
