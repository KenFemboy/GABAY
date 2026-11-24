"""Create assessments and documents tables.

Revision ID: 0004_assessments
Revises: 0003_learners
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_assessments"
down_revision: Union[str, Sequence[str], None] = "0003_learners"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "assessments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "learner_id",
            sa.Integer(),
            sa.ForeignKey("learners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("assessment_type", sa.String(16), nullable=False),
        sa.Column("assessment_date", sa.Date(), nullable=False),
        sa.Column("assessor", sa.String(150), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("processing_status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "assessment_type IN ('informal', 'formal')", name="ck_assessments_type"
        ),
        sa.CheckConstraint(
            "processing_status IN ('draft', 'uploaded', 'processing', 'processed', "
            "'needs_review', 'finalized')",
            name="ck_assessments_status",
        ),
    )
    op.create_index("ix_assessments_learner_id", "assessments", ["learner_id"])

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "assessment_id",
            sa.Integer(),
            sa.ForeignKey("assessments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(255), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("uploaded_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "uploaded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("assessment_id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index("ix_documents_checksum", "documents", ["checksum"])


def downgrade() -> None:
    op.drop_index("ix_documents_checksum", table_name="documents")
    op.drop_table("documents")
    op.drop_index("ix_assessments_learner_id", table_name="assessments")
    op.drop_table("assessments")
