"""Create ILAW tables: ilaw_entries, ilaw_alignments.

Revision ID: 0010_ilaw
Revises: 0009_iep
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010_ilaw"
down_revision: Union[str, Sequence[str], None] = "0009_iep"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ilaw_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("learner_id", sa.Integer(), sa.ForeignKey("learners.id", ondelete="CASCADE"), nullable=False),
        sa.Column("iep_id", sa.Integer(), sa.ForeignKey("ieps.id"), nullable=False),
        sa.Column("activity_date", sa.Date(), nullable=False),
        sa.Column("title", sa.String(150), nullable=False),
        sa.Column("title_key", sa.String(150), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("materials", sa.Text(), nullable=True),
        sa.Column("learner_response", sa.Text(), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("learner_id", "activity_date", "title_key", name="uq_ilaw_entries_learner_date_title"),
    )
    op.create_index("ix_ilaw_entries_learner_id", "ilaw_entries", ["learner_id"])

    op.create_table(
        "ilaw_alignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("entry_id", sa.Integer(), sa.ForeignKey("ilaw_entries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("iep_goal_id", sa.Integer(), sa.ForeignKey("iep_goals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="suggested"),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("model_version", sa.String(160), nullable=True),
        sa.Column("decided_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("entry_id", "iep_goal_id", name="uq_ilaw_alignments_entry_goal"),
        sa.CheckConstraint("status IN ('suggested', 'confirmed', 'rejected')", name="ck_ilaw_alignments_status"),
        sa.CheckConstraint("source IN ('suggested', 'manual')", name="ck_ilaw_alignments_source"),
    )
    op.create_index("ix_ilaw_alignments_entry_id", "ilaw_alignments", ["entry_id"])


def downgrade() -> None:
    op.drop_index("ix_ilaw_alignments_entry_id", table_name="ilaw_alignments")
    op.drop_table("ilaw_alignments")
    op.drop_index("ix_ilaw_entries_learner_id", table_name="ilaw_entries")
    op.drop_table("ilaw_entries")
