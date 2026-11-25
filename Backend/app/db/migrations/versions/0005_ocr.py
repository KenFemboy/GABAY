"""Create ocr_jobs and ocr_pages tables.

Revision ID: 0005_ocr
Revises: 0004_assessments
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_ocr"
down_revision: Union[str, Sequence[str], None] = "0004_assessments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ocr_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "assessment_id",
            sa.Integer(),
            sa.ForeignKey("assessments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            sa.Integer(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message", sa.String(500), nullable=True),
        sa.Column("requested_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "queued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')", name="ck_ocr_jobs_status"
        ),
    )
    op.create_index("ix_ocr_jobs_status_id", "ocr_jobs", ["status", "id"])
    op.create_index("ix_ocr_jobs_assessment_id", "ocr_jobs", ["assessment_id"])

    op.create_table(
        "ocr_pages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "document_id",
            sa.Integer(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "job_id", sa.Integer(), sa.ForeignKey("ocr_jobs.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("error_message", sa.String(500), nullable=True),
        sa.Column("reviewed_text", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("document_id", "page_number", name="uq_ocr_pages_document_page"),
        sa.CheckConstraint("source IN ('text_layer', 'ocr')", name="ck_ocr_pages_source"),
        sa.CheckConstraint("status IN ('ok', 'failed')", name="ck_ocr_pages_status"),
    )


def downgrade() -> None:
    op.drop_table("ocr_pages")
    op.drop_index("ix_ocr_jobs_assessment_id", table_name="ocr_jobs")
    op.drop_index("ix_ocr_jobs_status_id", table_name="ocr_jobs")
    op.drop_table("ocr_jobs")
