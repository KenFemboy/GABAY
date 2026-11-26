"""Create IEP tables: ieps, iep_findings, iep_goals.

Revision ID: 0009_iep
Revises: 0008_matching
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009_iep"
down_revision: Union[str, Sequence[str], None] = "0008_matching"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ieps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("learner_id", sa.Integer(), sa.ForeignKey("learners.id", ondelete="CASCADE"), nullable=False),
        sa.Column("school_year", sa.String(9), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("amends_iep_id", sa.Integer(), sa.ForeignKey("ieps.id", ondelete="SET NULL"), nullable=True),
        sa.Column("amendment_reason", sa.Text(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("annual_review_date", sa.Date(), nullable=True),
        sa.Column("accommodations", sa.Text(), nullable=True),
        sa.Column("services", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("team_members", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finalized_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("learner_id", "school_year", "version_number", name="uq_ieps_learner_year_version"),
        sa.CheckConstraint("status IN ('draft', 'finalized', 'superseded')", name="ck_ieps_status"),
    )
    op.create_index("ix_ieps_learner_id", "ieps", ["learner_id"])

    op.create_table(
        "iep_findings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("iep_id", sa.Integer(), sa.ForeignKey("ieps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("domain", sa.String(32), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "source_finding_id",
            sa.Integer(),
            sa.ForeignKey("extraction_findings.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_iep_findings_iep_id", "iep_findings", ["iep_id"])

    op.create_table(
        "iep_goals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("iep_id", sa.Integer(), sa.ForeignKey("ieps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column(
            "goal_recommendation_id",
            sa.Integer(),
            sa.ForeignKey("goal_recommendations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("goal_id", sa.Integer(), sa.ForeignKey("goals.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "goal_version_id", sa.Integer(), sa.ForeignKey("goal_versions.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column(
            "addresses_finding_id",
            sa.Integer(),
            sa.ForeignKey("iep_findings.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("domain", sa.String(32), nullable=True),
        sa.Column("skill_name", sa.String(120), nullable=True),
        sa.Column("goal_code", sa.String(16), nullable=True),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("measurement_method", sa.String(24), nullable=True),
        sa.Column("baseline", sa.Text(), nullable=True),
        sa.Column("baseline_value", sa.Float(), nullable=True),
        sa.Column("target_value", sa.Float(), nullable=True),
        sa.Column("target_unit", sa.String(16), nullable=True),
        sa.Column("criterion", sa.String(300), nullable=True),
        sa.Column("responsible_staff", sa.String(500), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("review_dates", sa.JSON(), nullable=False),
        sa.Column("match_score", sa.Float(), nullable=True),
        sa.CheckConstraint(
            "source IN ('accepted_recommendation', 'goal_bank', 'custom')", name="ck_iep_goals_source"
        ),
    )
    op.create_index("ix_iep_goals_iep_id", "iep_goals", ["iep_id"])


def downgrade() -> None:
    op.drop_index("ix_iep_goals_iep_id", table_name="iep_goals")
    op.drop_table("iep_goals")
    op.drop_index("ix_iep_findings_iep_id", table_name="iep_findings")
    op.drop_table("iep_findings")
    op.drop_index("ix_ieps_learner_id", table_name="ieps")
    op.drop_table("ieps")
