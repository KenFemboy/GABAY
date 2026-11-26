"""Create goal bank tables: taxonomy, goals, versions, usages, embeddings.

Revision ID: 0007_goal_bank
Revises: 0006_extraction
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_goal_bank"
down_revision: Union[str, Sequence[str], None] = "0006_extraction"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _now():
    return sa.func.now()


def upgrade() -> None:
    op.create_table(
        "goal_domains",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "goal_skills",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("domain_id", sa.Integer(), sa.ForeignKey("goal_domains.id"), nullable=False),
        sa.Column("code", sa.String(48), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("domain_id", "code", name="uq_goal_skills_domain_code"),
    )
    op.create_index("ix_goal_skills_domain_id", "goal_skills", ["domain_id"])

    op.create_table(
        "goals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(16), nullable=False, unique=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("current_version_id", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_now()),
        sa.CheckConstraint("status IN ('draft', 'active', 'archived')", name="ck_goals_status"),
    )
    op.create_table(
        "goal_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("goal_id", sa.Integer(), sa.ForeignKey("goals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("domain_id", sa.Integer(), sa.ForeignKey("goal_domains.id"), nullable=False),
        sa.Column("skill_id", sa.Integer(), sa.ForeignKey("goal_skills.id"), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("measurement_method", sa.String(24), nullable=False),
        sa.Column("target_value", sa.Float(), nullable=False),
        sa.Column("target_unit", sa.String(16), nullable=False),
        sa.Column("criterion", sa.String(300), nullable=True),
        sa.Column("grade_band", sa.String(8), nullable=False, server_default="any"),
        sa.Column("change_note", sa.String(300), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_now()),
        sa.UniqueConstraint("goal_id", "version_number", name="uq_goal_versions_number"),
        sa.CheckConstraint(
            "measurement_method IN ('percent_accuracy', 'trials', 'frequency', 'duration', "
            "'rate', 'rubric', 'checklist')",
            name="ck_goal_versions_method",
        ),
        sa.CheckConstraint(
            "target_unit IN ('percent', 'trials', 'count', 'minutes', 'wpm', 'level')",
            name="ck_goal_versions_unit",
        ),
        sa.CheckConstraint(
            "grade_band IN ('K-3', '4-6', '7-10', '11-12', 'any')", name="ck_goal_versions_grade_band"
        ),
    )
    op.create_index("ix_goal_versions_goal_id", "goal_versions", ["goal_id"])
    op.create_foreign_key(
        "fk_goals_current_version", "goals", "goal_versions", ["current_version_id"], ["id"]
    )

    op.create_table(
        "goal_usages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "goal_version_id",
            sa.Integer(),
            sa.ForeignKey("goal_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("usage_type", sa.String(32), nullable=False),
        sa.Column("reference_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_now()),
        sa.UniqueConstraint("goal_version_id", "usage_type", "reference_id", name="uq_goal_usages_ref"),
    )
    op.create_index("ix_goal_usages_goal_version_id", "goal_usages", ["goal_version_id"])

    op.create_table(
        "goal_embeddings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "goal_version_id",
            sa.Integer(),
            sa.ForeignKey("goal_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("text_hash", sa.String(64), nullable=False),
        sa.Column("dims", sa.Integer(), nullable=False),
        sa.Column("vector", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_now()),
        sa.UniqueConstraint("goal_version_id", "model", name="uq_goal_embeddings_version_model"),
    )


def downgrade() -> None:
    op.drop_table("goal_embeddings")
    op.drop_index("ix_goal_usages_goal_version_id", table_name="goal_usages")
    op.drop_table("goal_usages")
    op.drop_constraint("fk_goals_current_version", "goals", type_="foreignkey")
    op.drop_index("ix_goal_versions_goal_id", table_name="goal_versions")
    op.drop_table("goal_versions")
    op.drop_table("goals")
    op.drop_index("ix_goal_skills_domain_id", table_name="goal_skills")
    op.drop_table("goal_skills")
    op.drop_table("goal_domains")
