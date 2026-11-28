"""Create progress_records.

Revision ID: 0011_progress
Revises: 0010_ilaw
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011_progress"
down_revision: Union[str, Sequence[str], None] = "0010_ilaw"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "progress_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("learner_id", sa.Integer(), sa.ForeignKey("learners.id", ondelete="CASCADE"), nullable=False),
        sa.Column("iep_id", sa.Integer(), sa.ForeignKey("ieps.id"), nullable=False),
        sa.Column("iep_goal_id", sa.Integer(), sa.ForeignKey("iep_goals.id", ondelete="CASCADE"), nullable=True),
        sa.Column("ilaw_entry_id", sa.Integer(), sa.ForeignKey("ilaw_entries.id", ondelete="SET NULL"), nullable=True),
        sa.Column("evidence_type", sa.String(16), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("out_of", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(16), nullable=True),
        sa.Column("subject", sa.String(60), nullable=True),
        sa.Column("grading_period", sa.String(8), nullable=True),
        sa.Column("recorded_on", sa.Date(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "evidence_type IN ('probe', 'work_sample', 'test', 'observation', 'grade')",
            name="ck_progress_records_type",
        ),
        sa.CheckConstraint(
            "unit IS NULL OR unit IN ('percent', 'trials', 'count', 'minutes', 'wpm', 'level', 'grade')",
            name="ck_progress_records_unit",
        ),
        sa.CheckConstraint(
            "grading_period IS NULL OR grading_period IN ('Q1', 'Q2', 'Q3', 'Q4', 'final')",
            name="ck_progress_records_period",
        ),
    )
    op.create_index("ix_progress_records_learner_id", "progress_records", ["learner_id"])
    op.create_index("ix_progress_records_goal_date", "progress_records", ["iep_goal_id", "recorded_on"])


def downgrade() -> None:
    op.drop_index("ix_progress_records_goal_date", table_name="progress_records")
    op.drop_index("ix_progress_records_learner_id", table_name="progress_records")
    op.drop_table("progress_records")
