"""Goal embeddings with a local fastembed model (Stage 7).

* One vector per (goal version, model), enforced by a unique constraint.
* ``reindex`` embeds the current version of every ACTIVE goal, skips rows whose
  text hash is unchanged, updates stale rows in place, and removes rows that are
  no longer needed (archived goals, old versions, other models). Running it
  twice in a row changes nothing.
* ``search`` ranks active goals by cosine similarity to a query (Stage 8 uses it).

The model runs on this server; no text is sent to an external service.
"""

import hashlib
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import APIError
from app.models.goal import Goal, GoalEmbedding, GoalStatus, GoalVersion

logger = logging.getLogger(__name__)

BATCH_SIZE = 64


class EmbeddingUnavailable(Exception):
    """The embedding model could not be loaded or run."""


class Embedder(Protocol):
    model: str

    def embed(self, texts: list[str]) -> np.ndarray:
        """Return an (n, dims) float32 array of L2-normalised vectors."""


def _normalize(vectors: np.ndarray) -> np.ndarray:
    vectors = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


class FastEmbedEmbedder:
    """Lazy wrapper: the ONNX model is downloaded/loaded on first use."""

    def __init__(self, model: str, cache_dir: str) -> None:
        self.model = model
        self.cache_dir = cache_dir
        self._impl = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._impl is None:
                try:
                    from fastembed import TextEmbedding

                    Path(self.cache_dir).mkdir(parents=True, exist_ok=True)
                    logger.info("Loading embedding model %s (first use may download it)", self.model)
                    self._impl = TextEmbedding(model_name=self.model, cache_dir=self.cache_dir)
                except Exception as exc:  # network, disk, unsupported model ...
                    raise EmbeddingUnavailable(f"Could not load embedding model: {exc.__class__.__name__}") from exc
        return self._impl

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        impl = self._load()
        try:
            vectors = list(impl.embed(texts, batch_size=BATCH_SIZE))
        except Exception as exc:
            raise EmbeddingUnavailable(f"Embedding failed: {exc.__class__.__name__}") from exc
        return _normalize(np.vstack(vectors))


_default: FastEmbedEmbedder | None = None


def get_embedder() -> Embedder:
    """FastAPI dependency / process-wide singleton; tests override it."""
    global _default
    settings = get_settings()
    if _default is None or _default.model != settings.embedding_model:
        _default = FastEmbedEmbedder(settings.embedding_model, settings.embedding_cache_dir)
    return _default


def embeddings_unavailable(exc: Exception | None = None) -> APIError:
    return APIError(
        503,
        "embeddings_unavailable",
        "The goal embedding model is not available yet. Try again later or ask the administrator.",
    )


# --- Text and vectors ----------------------------------------------------------


def embedding_text(version: GoalVersion) -> str:
    return f"{version.domain.name} – {version.skill.name}: {version.statement.strip()}"


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def to_bytes(vector: np.ndarray) -> bytes:
    return np.asarray(vector, dtype=np.float32).tobytes()


def from_bytes(data: bytes) -> np.ndarray:
    return np.frombuffer(data, dtype=np.float32)


# --- Indexing ------------------------------------------------------------------


def _targets(db: Session) -> list[GoalVersion]:
    """Current versions of active goals."""
    return list(
        db.scalars(
            select(GoalVersion)
            .join(Goal, Goal.current_version_id == GoalVersion.id)
            .where(Goal.status == GoalStatus.ACTIVE.value)
        ).unique()
    )


@dataclass
class IndexStatus:
    model: str
    active_goals: int
    indexed: int
    missing_or_stale: int


def index_status(db: Session, model: str | None = None) -> IndexStatus:
    model = model or get_settings().embedding_model
    targets = _targets(db)
    rows = {
        r.goal_version_id: r.text_hash
        for r in db.scalars(select(GoalEmbedding).where(GoalEmbedding.model == model))
    }
    indexed = sum(1 for v in targets if rows.get(v.id) == text_hash(embedding_text(v)))
    return IndexStatus(model=model, active_goals=len(targets), indexed=indexed, missing_or_stale=len(targets) - indexed)


def reindex(db: Session, embedder: Embedder) -> dict[str, int]:
    targets = _targets(db)
    target_ids = {v.id for v in targets}
    existing = {
        r.goal_version_id: r
        for r in db.scalars(select(GoalEmbedding).where(GoalEmbedding.model == embedder.model))
    }

    todo: list[tuple[GoalVersion, str, str]] = []
    unchanged = 0
    for version in targets:
        text = embedding_text(version)
        digest = text_hash(text)
        row = existing.get(version.id)
        if row is not None and row.text_hash == digest:
            unchanged += 1
        else:
            todo.append((version, text, digest))

    created = updated = 0
    for start in range(0, len(todo), BATCH_SIZE):
        batch = todo[start:start + BATCH_SIZE]
        vectors = embedder.embed([text for _, text, _ in batch])
        for (version, _, digest), vector in zip(batch, vectors, strict=True):
            row = existing.get(version.id)
            if row is None:
                db.add(
                    GoalEmbedding(
                        goal_version_id=version.id,
                        model=embedder.model,
                        text_hash=digest,
                        dims=int(vector.shape[0]),
                        vector=to_bytes(vector),
                    )
                )
                created += 1
            else:
                row.text_hash = digest
                row.dims = int(vector.shape[0])
                row.vector = to_bytes(vector)
                updated += 1

    # Remove vectors that are no longer wanted: other models, archived goals, old versions.
    stale_ids = [
        r.id
        for r in db.scalars(select(GoalEmbedding))
        if r.model != embedder.model or r.goal_version_id not in target_ids
    ]
    if stale_ids:
        db.execute(delete(GoalEmbedding).where(GoalEmbedding.id.in_(stale_ids)))
    db.commit()
    result = {"created": created, "updated": updated, "unchanged": unchanged, "removed": len(stale_ids)}
    logger.info("Goal reindex: %s", result)
    return result


def reindex_if_needed(db: Session, embedder: Embedder) -> dict[str, int] | None:
    """Cheap check used by the worker loop; reindexes only when something is missing/stale."""
    status = index_status(db, embedder.model)
    extra = db.scalars(
        select(GoalEmbedding.id).where(GoalEmbedding.model == embedder.model)
    ).all()
    if status.missing_or_stale == 0 and len(extra) == status.indexed:
        return None
    return reindex(db, embedder)


# --- Search ----------------------------------------------------------------------


@dataclass
class SearchHit:
    goal: Goal
    score: float


def search(db: Session, query: str, embedder: Embedder, k: int = 10) -> list[SearchHit]:
    rows = db.execute(
        select(GoalEmbedding, Goal)
        .join(Goal, Goal.current_version_id == GoalEmbedding.goal_version_id)
        .where(Goal.status == GoalStatus.ACTIVE.value, GoalEmbedding.model == embedder.model)
    ).unique().all()
    if not rows:
        return []
    matrix = np.vstack([from_bytes(r.GoalEmbedding.vector) for r in rows])
    query_vec = embedder.embed([query])[0]
    if query_vec.shape[0] != matrix.shape[1]:
        raise EmbeddingUnavailable("Stored vectors do not match the model; run reindex.")
    scores = matrix @ query_vec
    order = np.argsort(-scores)[:k]
    return [SearchHit(goal=rows[i].Goal, score=float(scores[i])) for i in order]
