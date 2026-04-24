"""add company charts share snapshots

Revision ID: 20260423_0038
Revises: 20260423_0037
Create Date: 2026-04-23 00:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260423_0038"
down_revision = "20260423_0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_charts_share_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=48), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "snapshot_hash", name="uq_company_charts_share_snapshots_company_hash"),
    )
    op.create_index(
        "ix_company_charts_share_snapshots_company_id",
        "company_charts_share_snapshots",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        "ix_company_charts_share_snapshots_company_created_at",
        "company_charts_share_snapshots",
        ["company_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_company_charts_share_snapshots_company_created_at", table_name="company_charts_share_snapshots")
    op.drop_index("ix_company_charts_share_snapshots_company_id", table_name="company_charts_share_snapshots")
    op.drop_table("company_charts_share_snapshots")
