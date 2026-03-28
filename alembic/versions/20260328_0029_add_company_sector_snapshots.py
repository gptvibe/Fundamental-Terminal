"""Add company sector context snapshots

Revision ID: 20260328_0029
Revises: 20260328_0028
Create Date: 2026-03-28 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260328_0029"
down_revision = "20260328_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_sector_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("is_stale", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "snapshot_date", name="uq_company_sector_snapshots_company_date"),
    )
    op.create_index("ix_company_sector_snapshots_company", "company_sector_snapshots", ["company_id"])
    op.create_index(
        "ix_company_sector_snapshots_company_date",
        "company_sector_snapshots",
        ["company_id", "snapshot_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_company_sector_snapshots_company_date", table_name="company_sector_snapshots")
    op.drop_index("ix_company_sector_snapshots_company", table_name="company_sector_snapshots")
    op.drop_table("company_sector_snapshots")