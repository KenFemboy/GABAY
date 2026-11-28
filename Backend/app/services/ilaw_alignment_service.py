"""Align ILAW activity entries with the goals of the learner's ACTIVE IEP (Stage 10).

Suggestions use the same local embedding model as the goal bank and matching.
An IEP has only a handful of goals, so the entry and the goals are embedded
together in one small batch and ranked with numpy; no vector table is needed.

Only the active IEP (the finalized version for the learner's current school
year) is ever used: drafts, amendment drafts and superseded versions are not.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import APIError, conflict, not_found
from app.models.iep import Iep, IepGoal, IepStatus
from app.models.ilaw import AlignmentSource, AlignmentStatus, IlawAlignment, IlawEntry
from app.models.learner import Learner
from app.models.user import User
from app.services.embedding_service import Embedder, check_dims
from app.services.iep_document import DOMAIN_NAMES

TEXT_VERSION = "ilaw-text-v1"

SUGGESTED = AlignmentStatus.SUGGESTED.value
CONFIRMED = AlignmentStatus.CONFIRMED.value
REJECTED = AlignmentStatus.REJECTED.value


def model_version(model: str) -> str:
    return f"{model}|{TEXT_VERSION}"


def _now() -> datetime:
    return datetime.now(UTC)


def active_iep(db: Session, learner: Learner) -> Iep | None:
    """The finalized IEP for the learner's current school year (never a draft or superseded one)."""
    return db.scalar(
        select(Iep)
        .where(
            Iep.learner_id == learner.id,
            Iep.school_year == learner.school_year,
            Iep.status == IepStatus.FINALIZED.value,
        )
        .order_by(Iep.version_number.desc())
        .limit(1)
    )


def entry_text(entry: IlawEntry) -> str:
    return f"{entry.title.strip()}. {entry.description.strip()}"


def goal_text(goal: IepGoal) -> str:
    name = DOMAIN_NAMES.get(goal.domain or "")
    return f"{name} – {goal.statement.strip()}" if name else goal.statement.strip()


def _require_active_goal(iep: Iep | None, iep_goal_id: int) -> IepGoal:
    if iep is None:
        raise conflict("no_active_iep", "The learner has no finalized IEP. Finalize the IEP first.")
    for goal in iep.goals:
        if goal.id == iep_goal_id:
            return goal
    raise APIError(422, "invalid_goal", "Choose a goal from the learner's active IEP.")


def _move_to_active(db: Session, entry: IlawEntry, learner: Learner) -> Iep:
    """Point the entry at the active IEP. Pending suggestions for old-version goals are dropped;
    decided links stay as history."""
    iep = active_iep(db, learner)
    if iep is None:
        raise conflict("no_active_iep", "The learner has no finalized IEP. Finalize the IEP first.")
    if entry.iep_id != iep.id:
        active_ids = {g.id for g in iep.goals}
        for link in list(entry.alignments):
            if link.iep_goal_id not in active_ids and link.status == SUGGESTED:
                entry.alignments.remove(link)
        entry.iep_id = iep.id
        db.flush()
    return iep


def suggest(
    db: Session,
    entry: IlawEntry,
    learner: Learner,
    embedder: Embedder,
    *,
    top_k: int | None = None,
    min_score: float | None = None,
) -> list[IlawAlignment]:
    """(Re)compute suggestions. Confirmed/rejected links are never changed. Commits."""
    settings = get_settings()
    top_k = top_k or settings.ilaw_top_k
    min_score = settings.ilaw_min_score if min_score is None else min_score
    iep = _move_to_active(db, entry, learner)
    goals = list(iep.goals)
    if not goals:
        db.commit()
        return list(entry.alignments)

    vectors = check_dims(embedder.embed([entry_text(entry)] + [goal_text(g) for g in goals]))
    scores = vectors[1:] @ vectors[0]
    order = sorted(range(len(goals)), key=lambda i: (-float(scores[i]), goals[i].position))
    picked = [(goals[i], float(scores[i])) for i in order if scores[i] >= min_score][:top_k]
    picked_ids = {g.id for g, _ in picked}
    version = model_version(embedder.model)

    existing = {link.iep_goal_id: link for link in entry.alignments}
    # Drop pending suggestions that are no longer in the top list.
    for link in list(entry.alignments):
        if link.status == SUGGESTED and link.source == AlignmentSource.SUGGESTED.value and link.iep_goal_id not in picked_ids:
            entry.alignments.remove(link)
    for rank, (goal, score) in enumerate(picked, 1):
        link = existing.get(goal.id)
        if link is None:
            entry.alignments.append(
                IlawAlignment(
                    iep_goal_id=goal.id,
                    source=AlignmentSource.SUGGESTED.value,
                    status=SUGGESTED,
                    score=round(score, 6),
                    rank=rank,
                    model_version=version,
                )
            )
        elif link.source == AlignmentSource.SUGGESTED.value:
            # Refresh score/rank; the decision (if any) is kept.
            link.score = round(score, 6)
            link.rank = rank
            link.model_version = version
    db.commit()
    db.refresh(entry)
    return list(entry.alignments)


# --- Decisions ----------------------------------------------------------------------------


def get_link(db: Session, link_id: int) -> IlawAlignment:
    link = db.get(IlawAlignment, link_id)
    if link is None:
        raise not_found("Link not found.")
    return link


def _decide(link: IlawAlignment, user: User, status: str) -> None:
    link.status = status
    link.decided_by = user.id
    link.decided_at = _now()


def confirm(db: Session, user: User, link: IlawAlignment) -> IlawAlignment:
    _decide(link, user, CONFIRMED)
    db.commit()
    db.refresh(link)
    return link


def reject(db: Session, user: User, link: IlawAlignment) -> IlawAlignment:
    _decide(link, user, REJECTED)
    db.commit()
    db.refresh(link)
    return link


def reset(db: Session, link: IlawAlignment) -> IlawAlignment:
    if link.source == AlignmentSource.MANUAL.value:
        # A manual link has no suggestion to go back to; undoing removes it.
        db.delete(link)
        db.commit()
        return link
    link.status = SUGGESTED
    link.decided_by = None
    link.decided_at = None
    db.commit()
    db.refresh(link)
    return link


def add_manual(db: Session, user: User, entry: IlawEntry, learner: Learner, iep_goal_id: int) -> IlawAlignment:
    iep = _move_to_active(db, entry, learner)
    _require_active_goal(iep, iep_goal_id)
    link = next((a for a in entry.alignments if a.iep_goal_id == iep_goal_id), None)
    if link is None:
        link = IlawAlignment(iep_goal_id=iep_goal_id, source=AlignmentSource.MANUAL.value, status=CONFIRMED)
        entry.alignments.append(link)
    _decide(link, user, CONFIRMED)
    db.commit()
    db.refresh(link)
    return link


def change(db: Session, user: User, link: IlawAlignment, learner: Learner, new_goal_id: int) -> IlawAlignment:
    """Reject this link and confirm a link to another goal of the active IEP instead."""
    if link.iep_goal_id == new_goal_id:
        return confirm(db, user, link)
    entry = link.entry
    iep = _move_to_active(db, entry, learner)
    _require_active_goal(iep, new_goal_id)
    if link in entry.alignments:  # may have been dropped if it pointed at an old IEP version
        _decide(link, user, REJECTED)
    return add_manual(db, user, entry, learner, new_goal_id)


# --- Read helpers for later stages (progress monitoring) -------------------------------------


def confirmed_goal_ids(entry: IlawEntry) -> list[int]:
    return [a.iep_goal_id for a in entry.alignments if a.status == CONFIRMED]


def entries_for_goal(db: Session, iep_goal_id: int) -> list[IlawEntry]:
    return list(
        db.scalars(
            select(IlawEntry)
            .join(IlawAlignment, IlawAlignment.entry_id == IlawEntry.id)
            .where(IlawAlignment.iep_goal_id == iep_goal_id, IlawAlignment.status == CONFIRMED)
            .order_by(IlawEntry.activity_date)
        ).unique()
    )

