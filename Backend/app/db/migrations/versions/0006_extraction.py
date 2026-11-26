"""Create extraction_versions and extraction_findings tables.

Revision ID: 0006_extraction
Revises: 0005_ocr
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_extraction"
down_revision: Union[str, Sequence[str], None] = "0005_ocr"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CATEGORIES = "'diagnosis', 'strength', 'need', 'present_level', 'recommendation'"
DOMAINS = (
    "'reading', 'writing', 'mathematics', 'behavior_social', 'communication', 'motor', "
    "'self_help', 'cognitive', 'other'"
)


def upgrade() -> None:
    op.create_table(
        "extraction_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "assessment_id",
            sa.Integer(),
            sa.ForeignKey("assessments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column(
            "based_on_version_id",
            sa.Integer(),
            sa.ForeignKey("extraction_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_text_hash", sa.String(64), nullable=False),
        sa.Column("extractor_version", sa.String(32), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("assessment_id", "version_number", name="uq_extraction_versions_number"),
        sa.CheckConstraint("method IN ('rule', 'ai', 'manual')", name="ck_extraction_versions_method"),
        sa.CheckConstraint(
            "status IN ('draft', 'approved', 'superseded')", name="ck_extraction_versions_status"
        ),
    )
    op.create_index(
        "ix_extraction_versions_assessment_id", "extraction_versions", ["assessment_id"]
    )

    op.create_table(
        "extraction_findings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "version_id",
            sa.Integer(),
            sa.ForeignKey("extraction_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("domain", sa.String(32), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_page", sa.Integer(), nullable=True),
        sa.Column("source_start", sa.Integer(), nullable=True),
        sa.Column("source_end", sa.Integer(), nullable=True),
        sa.Column("source_quote", sa.String(500), nullable=True),
        sa.Column("origin", sa.String(16), nullable=False),
        sa.Column("edited", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.CheckConstraint(f"category IN ({CATEGORIES})", name="ck_extraction_findings_category"),
        sa.CheckConstraint(
            f"domain IS NULL OR domain IN ({DOMAINS})", name="ck_extraction_findings_domain"
        ),
        sa.CheckConstraint("origin IN ('extracted', 'manual')", name="ck_extraction_findings_origin"),
    )
    op.create_index("ix_extraction_findings_version_id", "extraction_findings", ["version_id"])


def downgrade() -> None:
    op.drop_index("ix_extraction_findings_version_id", table_name="extraction_findings")
    op.drop_table("extraction_findings")
    op.drop_index("ix_extraction_versions_assessment_id", table_name="extraction_versions")
    op.drop_table("extraction_versions")
