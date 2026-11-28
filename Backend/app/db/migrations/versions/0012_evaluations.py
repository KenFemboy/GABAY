"""Create evaluations (year-end evaluation).

Revision ID: 0012_evaluations
Revises: 0011_progress
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012_evaluations"
down_revision: Union[str, Sequence[str], None] = "0011_progress"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "evaluations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("learner_id", sa.Integer(), sa.ForeignKey("learners.id", ondelete="CASCADE"), nullable=False),
        sa.Column("iep_id", sa.Integer(), sa.ForeignKey("ieps.id"), nullable=False),
        sa.Column("school_year", sa.String(9), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("model", sa.String(120), nullable=True),
        sa.Column("prompt_version", sa.String(40), nullable=True),
        sa.Column("evidence_ids", sa.JSON(), nullable=False),
        sa.Column("evidence_hash", sa.String(64), nullable=True),
        sa.Column("evidence_snapshot", sa.JSON(), nullable=False),
        sa.Column("raw_response", sa.Text(), nullable=True),
        sa.Column("validation_warnings", sa.JSON(), nullable=False),
        sa.Column("generation_error", sa.String(500), nullable=True),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finalized_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('draft', 'finalized')", name="ck_evaluations_status"),
        sa.CheckConstraint("source IN ('ai', 'manual')", name="ck_evaluations_source"),
    )
    op.create_index("ix_evaluations_learner_id", "evaluations", ["learner_id"])


def downgrade() -> None:
    op.drop_index("ix_evaluations_learner_id", table_name="evaluations")
    op.drop_table("evaluations")
