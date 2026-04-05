"""add company research brief snapshots

Revision ID: 20260405_0033
Revises: 20260404_0032
Create Date: 2026-04-05 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260405_0033"
down_revision = "20260404_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_research_brief_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("as_of_key", sa.String(length=64), server_default="latest", nullable=False),
        sa.Column("as_of_value", sa.DateTime(timezone=True), nullable=True),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("last_updated", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_checked", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "as_of_key", "schema_version", name="uq_company_research_brief_snapshots_company_asof_schema"),
    )
    op.create_index("ix_company_research_brief_snapshots_company_id", "company_research_brief_snapshots", ["company_id"], unique=False)
    op.create_index(
        "ix_company_research_brief_snapshots_company_as_of",
        "company_research_brief_snapshots",
        ["company_id", "as_of_key"],
        unique=False,
    )
    op.create_index(
        "ix_company_research_brief_snapshots_company_last_checked",
        "company_research_brief_snapshots",
        ["company_id", "last_checked"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_company_research_brief_snapshots_company_last_checked", table_name="company_research_brief_snapshots")
    op.drop_index("ix_company_research_brief_snapshots_company_as_of", table_name="company_research_brief_snapshots")
    op.drop_index("ix_company_research_brief_snapshots_company_id", table_name="company_research_brief_snapshots")
    op.drop_table("company_research_brief_snapshots")