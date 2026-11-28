"""ILAW (daily learning activity log) and IEP goal alignment API (Stage 10)."""

from datetime import date

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.permissions import require_assessment_writers, require_learner_readers
from app.db.session import get_db
from app.models.ilaw import IlawAlignment, IlawEntry
from app.models.learner import Learner
from app.models.user import User
from app.schemas.ilaw import (
    ActiveIep,
    ActiveIepRead,
    EntryCreate,
    EntryList,
    EntryRead,
    EntryUpdate,
    GoalChoice,
    GoalRef,
    LinkRead,
)
from app.services import ilaw_alignment_service as alignment
from app.services import ilaw_service, learner_service
from app.services.embedding_service import Embedder, get_embedder

router = APIRouter(prefix="/api", tags=["ilaw"])


def _entry(db: Session, entry_id: int, user: User) -> tuple[IlawEntry, Learner]:
    entry = ilaw_service.get_entry(db, entry_id)
    learner = learner_service.get_visible_learner(db, entry.learner_id, user)
    return entry, learner


def _link(db: Session, link_id: int, user: User) -> tuple[IlawAlignment, Learner]:
    link = alignment.get_link(db, link_id)
    learner = learner_service.get_visible_learner(db, link.entry.learner_id, user)
    return link, learner


def _read(entry: IlawEntry, error: str | None = None) -> EntryRead:
    return EntryRead.model_validate(entry).model_copy(update={"suggestions_error": error})


@router.get("/learners/{learner_id}/ilaw/active-iep", response_model=ActiveIep)
def get_active_iep(learner_id: int, db: Session = Depends(get_db), user: User = Depends(require_learner_readers)):
    learner = learner_service.get_visible_learner(db, learner_id, user)
    iep = alignment.active_iep(db, learner)
    if iep is None:
        return ActiveIep(iep=None)
    return ActiveIep(
        iep=ActiveIepRead(
            id=iep.id, version_number=iep.version_number, school_year=iep.school_year,
            start_date=iep.start_date, end_date=iep.end_date,
            goals=[GoalRef.model_validate(g) for g in iep.goals],
        )
    )


@router.get("/learners/{learner_id}/ilaw", response_model=EntryList)
def list_entries(
    learner_id: int,
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    goal: int | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(require_learner_readers),
) -> EntryList:
    learner = learner_service.get_visible_learner(db, learner_id, user)
    items, total = ilaw_service.list_entries(
        db, learner.id, date_from=date_from, date_to=date_to, iep_goal_id=goal, offset=offset, limit=limit
    )
    return EntryList(items=[_read(e) for e in items], total=total)


@router.post("/learners/{learner_id}/ilaw", response_model=EntryRead, status_code=status.HTTP_201_CREATED)
def create_entry(
    learner_id: int,
    payload: EntryCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_assessment_writers),
    embedder: Embedder = Depends(get_embedder),
) -> EntryRead:
    learner = learner_service.get_visible_learner(db, learner_id, user)
    entry, error = ilaw_service.create_entry(db, user, learner, payload.model_dump(), embedder)
    return _read(entry, error)


@router.get("/ilaw/{entry_id}", response_model=EntryRead)
def get_entry(entry_id: int, db: Session = Depends(get_db), user: User = Depends(require_learner_readers)):
    return _read(_entry(db, entry_id, user)[0])


@router.patch("/ilaw/{entry_id}", response_model=EntryRead)
def update_entry(
    entry_id: int,
    payload: EntryUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_assessment_writers),
    embedder: Embedder = Depends(get_embedder),
) -> EntryRead:
    entry, learner = _entry(db, entry_id, user)
    changes = {
        k: v for k, v in payload.model_dump(exclude_unset=True).items()
        if v is not None or k in ("materials", "learner_response", "duration_minutes", "notes")
    }
    entry, error = ilaw_service.update_entry(db, entry, learner, changes, embedder)
    return _read(entry, error)


@router.delete("/ilaw/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(entry_id: int, db: Session = Depends(get_db), user: User = Depends(require_assessment_writers)):
    entry, _ = _entry(db, entry_id, user)
    ilaw_service.delete_entry(db, entry)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/ilaw/{entry_id}/suggest", response_model=EntryRead)
def resuggest(
    entry_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_assessment_writers),
    embedder: Embedder = Depends(get_embedder),
) -> EntryRead:
    entry, learner = _entry(db, entry_id, user)
    entry, error = ilaw_service.resuggest(db, entry, learner, embedder)
    return _read(entry, error)


@router.post("/ilaw/{entry_id}/links", response_model=LinkRead, status_code=status.HTTP_201_CREATED)
def add_link(entry_id: int, payload: GoalChoice, db: Session = Depends(get_db), user: User = Depends(require_assessment_writers)):
    entry, learner = _entry(db, entry_id, user)
    return alignment.add_manual(db, user, entry, learner, payload.iep_goal_id)


@router.post("/ilaw-links/{link_id}/confirm", response_model=LinkRead)
def confirm(link_id: int, db: Session = Depends(get_db), user: User = Depends(require_assessment_writers)):
    link, _ = _link(db, link_id, user)
    return alignment.confirm(db, user, link)


@router.post("/ilaw-links/{link_id}/reject", response_model=LinkRead)
def reject(link_id: int, db: Session = Depends(get_db), user: User = Depends(require_assessment_writers)):
    link, _ = _link(db, link_id, user)
    return alignment.reject(db, user, link)


@router.post("/ilaw-links/{link_id}/reset", status_code=status.HTTP_204_NO_CONTENT)
def reset(link_id: int, db: Session = Depends(get_db), user: User = Depends(require_assessment_writers)):
    link, _ = _link(db, link_id, user)
    alignment.reset(db, link)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/ilaw-links/{link_id}/change", response_model=LinkRead)
def change(link_id: int, payload: GoalChoice, db: Session = Depends(get_db), user: User = Depends(require_assessment_writers)):
    link, learner = _link(db, link_id, user)
    return alignment.change(db, user, link, learner, payload.iep_goal_id)
