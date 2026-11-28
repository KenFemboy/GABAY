"""ILAW activity entries (Stage 10): create, update, list, delete.

Duplicate rule: one entry per learner + activity date + activity title, where
the title is compared case- and whitespace-insensitively (``title_key``). The
database enforces the same rule with a unique constraint.
"""

import re
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import APIError, conflict, not_found
from app.models.iep import Iep
from app.models.ilaw import IlawAlignment, IlawEntry
from app.models.learner import Learner
from app.models.user import User
from app.services import ilaw_alignment_service as alignment
from app.services import learner_service
from app.services.embedding_service import Embedder, EmbeddingUnavailable

ENTRY_FIELDS = ("activity_date", "title", "description", "materials", "learner_response", "duration_minutes", "notes")


def title_key(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip().lower()


def get_entry(db: Session, entry_id: int) -> IlawEntry:
    entry = db.get(IlawEntry, entry_id)
    if entry is None:
        raise not_found("Activity entry not found.")
    return entry


def _duplicate(db: Session, learner_id: int, activity_date: date, key: str, exclude_id: int | None = None) -> bool:
    query = select(IlawEntry.id).where(
        IlawEntry.learner_id == learner_id, IlawEntry.activity_date == activity_date, IlawEntry.title_key == key
    )
    if exclude_id is not None:
        query = query.where(IlawEntry.id != exclude_id)
    return db.scalar(query) is not None


def duplicate_error() -> APIError:
    return conflict("duplicate_entry", "An activity with this title is already logged for this learner on that date.")


def _check_date(iep, activity_date: date) -> None:
    if activity_date > date.today():
        raise APIError(422, "future_date", "The activity date cannot be in the future.")
    if iep.start_date and iep.end_date and not (iep.start_date <= activity_date <= iep.end_date):
        raise APIError(
            422,
            "outside_iep_period",
            f"The activity date must be within the IEP period ({iep.start_date.isoformat()} to {iep.end_date.isoformat()}).",
        )


def _commit_entry(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:  # race with a concurrent identical entry
        db.rollback()
        raise duplicate_error() from exc


def _suggest(db: Session, entry: IlawEntry, learner: Learner, embedder: Embedder) -> str | None:
    """Run suggestions; return an error message instead of failing the save."""
    try:
        alignment.suggest(db, entry, learner, embedder)
        return None
    except EmbeddingUnavailable:
        db.rollback()
        return "Goal suggestions are not available right now. You can link goals by hand or retry later."


def create_entry(db: Session, user: User, learner: Learner, data: dict, embedder: Embedder) -> tuple[IlawEntry, str | None]:
    iep = alignment.active_iep(db, learner)
    if iep is None:
        raise conflict("no_active_iep", "Finalize the learner's IEP before logging activities.")
    _check_date(iep, data["activity_date"])
    key = title_key(data["title"])
    if _duplicate(db, learner.id, data["activity_date"], key):
        raise duplicate_error()
    entry = IlawEntry(
        learner_id=learner.id,
        iep_id=iep.id,
        title_key=key,
        created_by=user.id,
        **{k: data.get(k) for k in ENTRY_FIELDS},
    )
    db.add(entry)
    _commit_entry(db)
    db.refresh(entry)
    error = _suggest(db, entry, learner, embedder)
    db.refresh(entry)
    return entry, error


def update_entry(
    db: Session, entry: IlawEntry, learner: Learner, changes: dict, embedder: Embedder
) -> tuple[IlawEntry, str | None]:
    new_date = changes.get("activity_date", entry.activity_date)
    new_title = changes.get("title", entry.title)
    key = title_key(new_title)
    if (new_date, key) != (entry.activity_date, entry.title_key) and _duplicate(db, learner.id, new_date, key, entry.id):
        raise duplicate_error()
    if "activity_date" in changes:
        _check_date(alignment.active_iep(db, learner) or db.get(Iep, entry.iep_id), new_date)
    text_changed = any(k in changes and changes[k] != getattr(entry, k) for k in ("title", "description"))
    for key_name, value in changes.items():
        if key_name in ENTRY_FIELDS:
            setattr(entry, key_name, value)
    entry.title_key = key
    _commit_entry(db)
    db.refresh(entry)
    error = _suggest(db, entry, learner, embedder) if text_changed else None
    db.refresh(entry)
    return entry, error


def resuggest(db: Session, entry: IlawEntry, learner: Learner, embedder: Embedder) -> tuple[IlawEntry, str | None]:
    error = _suggest(db, entry, learner, embedder)
    db.refresh(entry)
    return entry, error


def delete_entry(db: Session, entry: IlawEntry) -> None:
    db.delete(entry)
    db.commit()


def list_entries(
    db: Session,
    learner_id: int,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    iep_goal_id: int | None = None,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[IlawEntry], int]:
    query = select(IlawEntry).where(IlawEntry.learner_id == learner_id)
    if date_from:
        query = query.where(IlawEntry.activity_date >= date_from)
    if date_to:
        query = query.where(IlawEntry.activity_date <= date_to)
    if iep_goal_id:
        query = query.where(
            IlawEntry.id.in_(
                select(IlawAlignment.entry_id).where(
                    IlawAlignment.iep_goal_id == iep_goal_id, IlawAlignment.status == alignment.CONFIRMED
                )
            )
        )
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.order_by(IlawEntry.activity_date.desc(), IlawEntry.id.desc()).offset(offset).limit(limit)
    ).unique()
    return list(items), total


def summary_for_learner(db: Session, learner_id: int) -> tuple[int, str | None, datetime | None]:
    count = db.scalar(select(func.count(IlawEntry.id)).where(IlawEntry.learner_id == learner_id)) or 0
    latest = db.scalar(
        select(IlawEntry.activity_date).where(IlawEntry.learner_id == learner_id).order_by(IlawEntry.activity_date.desc()).limit(1)
    )
    latest_at = datetime.combine(latest, datetime.min.time()) if latest else None
    return count, ("logged" if count else None), latest_at


learner_service.MODULE_COUNTERS["ilaw"] = summary_for_learner
