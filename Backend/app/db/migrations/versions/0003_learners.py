"""Create learners and learner_assignments tables.

Revision ID: 0003_learners
Revises: 0002_users
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_learners"
down_revision: Union[str, Sequence[str], None] = "0002_users"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "learners",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("learner_code", sa.String(32), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("middle_name", sa.String(100), nullable=True),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("birth_date", sa.Date(), nullable=False),
        sa.Column("sex", sa.String(8), nullable=False),
        sa.Column("grade_level", sa.String(4), nullable=False),
        sa.Column("section", sa.String(50), nullable=False),
        sa.Column("school_year", sa.String(9), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status IN ('active', 'transferred', 'graduated', 'inactive')",
            name="ck_learners_status",
        ),
        sa.CheckConstraint("sex IN ('male', 'female')", name="ck_learners_sex"),
        sa.CheckConstraint(
            "grade_level IN ('K', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12', 'NG')",
            name="ck_learners_grade_level",
        ),
    )
    op.create_index("ix_learners_learner_code", "learners", ["learner_code"], unique=True)
    op.create_index("ix_learners_name", "learners", ["last_name", "first_name"])
    op.create_index("ix_learners_school_year", "learners", ["school_year"])
    op.create_index("ix_learners_status", "learners", ["status"])

    op.create_table(
        "learner_assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "learner_id",
            sa.Integer(),
            sa.ForeignKey("learners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("school_year", sa.String(9), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("learner_id", "user_id", "school_year", name="uq_learner_assignments"),
    )
    op.create_index("ix_learner_assignments_learner_id", "learner_assignments", ["learner_id"])
    op.create_index("ix_learner_assignments_user_id", "learner_assignments", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_learner_assignments_user_id", table_name="learner_assignments")
    op.drop_index("ix_learner_assignments_learner_id", table_name="learner_assignments")
    op.drop_table("learner_assignments")
    op.drop_index("ix_learners_status", table_name="learners")
    op.drop_index("ix_learners_school_year", table_name="learners")
    op.drop_index("ix_learners_name", table_name="learners")
    op.drop_index("ix_learners_learner_code", table_name="learners")
    op.drop_table("learners")
