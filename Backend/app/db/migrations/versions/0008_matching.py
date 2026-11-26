"""Enable pgvector; move goal vectors to vector(384); add matching tables.

Revision ID: 0008_matching
Revises: 0007_goal_bank

PostgreSQL needs the pgvector extension files installed on the server first
(see README "Install pgvector"). On other databases (SQLite in tests) only the
tables are created and vectors stay as bytes.
"""
from typing import Sequence, Union

import numpy as np
import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import VECTOR

revision: str = "0008_matching"
down_revision: Union[str, Sequence[str], None] = "0007_goal_bank"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DIMS = 384


def _is_pg() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _vector_type():
    return VECTOR(DIMS) if _is_pg() else sa.LargeBinary()


def upgrade() -> None:
    bind = op.get_bind()
    if _is_pg():
        available = bind.execute(
            sa.text("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")
        ).scalar()
        if not available:
            raise RuntimeError(
                "The pgvector extension is not installed on this PostgreSQL server. "
                "Install it first (README: 'Install pgvector'), then run 'alembic upgrade head' again."
            )
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

        # goal_embeddings.vector: bytea (float32) -> vector(384), keeping existing rows.
        op.add_column("goal_embeddings", sa.Column("vector_new", VECTOR(DIMS), nullable=True))
        rows = bind.execute(sa.text("SELECT id, vector FROM goal_embeddings")).fetchall()
        for row_id, raw in rows:
            values = np.frombuffer(bytes(raw), dtype=np.float32)
            if values.shape[0] != DIMS:
                bind.execute(sa.text("DELETE FROM goal_embeddings WHERE id = :id"), {"id": row_id})
                continue
            bind.execute(
                sa.text("UPDATE goal_embeddings SET vector_new = CAST(:v AS vector) WHERE id = :id"),
                {"v": "[" + ",".join(f"{x:.8g}" for x in values) + "]", "id": row_id},
            )
        op.drop_column("goal_embeddings", "vector")
        op.alter_column("goal_embeddings", "vector_new", new_column_name="vector", nullable=False)
        op.execute(
            "CREATE INDEX ix_goal_embeddings_vector_hnsw ON goal_embeddings "
            "USING hnsw (vector vector_cosine_ops)"
        )

    op.create_table(
        "need_embeddings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "finding_id",
            sa.Integer(),
            sa.ForeignKey("extraction_findings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("text_hash", sa.String(64), nullable=False),
        sa.Column("embedding", _vector_type(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("finding_id", "model", name="uq_need_embeddings_finding_model"),
    )

    op.create_table(
        "matching_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("learner_id", sa.Integer(), sa.ForeignKey("learners.id", ondelete="CASCADE"), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("model_version", sa.String(160), nullable=False),
        sa.Column("top_k", sa.Integer(), nullable=False),
        sa.Column("min_score", sa.Float(), nullable=False),
        sa.Column("same_domain", sa.Boolean(), nullable=False),
        sa.Column("grade_band", sa.String(8), nullable=True),
        sa.Column("need_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_matching_runs_learner_id", "matching_runs", ["learner_id"])

    op.create_table(
        "goal_recommendations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("matching_runs.id", ondelete="CASCADE"), nullable=True),
        sa.Column("learner_id", sa.Integer(), sa.ForeignKey("learners.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "finding_id",
            sa.Integer(),
            sa.ForeignKey("extraction_findings.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("goal_id", sa.Integer(), sa.ForeignKey("goals.id"), nullable=False),
        sa.Column("goal_version_id", sa.Integer(), sa.ForeignKey("goal_versions.id"), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("model_version", sa.String(160), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="suggested"),
        sa.Column("edited_statement", sa.Text(), nullable=True),
        sa.Column("edited_target_value", sa.Float(), nullable=True),
        sa.Column("edited_criterion", sa.String(300), nullable=True),
        sa.Column("reject_reason", sa.String(300), nullable=True),
        sa.Column("decided_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("run_id", "finding_id", "goal_version_id", name="uq_goal_recommendations_run"),
        sa.CheckConstraint(
            "status IN ('suggested', 'accepted', 'rejected')", name="ck_goal_recommendations_status"
        ),
        sa.CheckConstraint("source IN ('matched', 'manual')", name="ck_goal_recommendations_source"),
    )
    op.create_index("ix_goal_recommendations_learner_id", "goal_recommendations", ["learner_id"])


def downgrade() -> None:
    op.drop_index("ix_goal_recommendations_learner_id", table_name="goal_recommendations")
    op.drop_table("goal_recommendations")
    op.drop_index("ix_matching_runs_learner_id", table_name="matching_runs")
    op.drop_table("matching_runs")
    op.drop_table("need_embeddings")
    if _is_pg():
        bind = op.get_bind()
        op.execute("DROP INDEX IF EXISTS ix_goal_embeddings_vector_hnsw")
        op.add_column("goal_embeddings", sa.Column("vector_old", sa.LargeBinary(), nullable=True))
        rows = bind.execute(sa.text("SELECT id, vector::text FROM goal_embeddings")).fetchall()
        for row_id, text_value in rows:
            values = np.array([float(x) for x in text_value.strip("[]").split(",")], dtype=np.float32)
            bind.execute(
                sa.text("UPDATE goal_embeddings SET vector_old = :v WHERE id = :id"),
                {"v": values.tobytes(), "id": row_id},
            )
        op.drop_column("goal_embeddings", "vector")
        op.alter_column("goal_embeddings", "vector_old", new_column_name="vector", nullable=False)
        # The extension itself is left installed; other objects may depend on it.
