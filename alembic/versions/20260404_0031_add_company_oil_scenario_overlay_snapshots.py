"""Add company oil scenario overlay snapshots

Revision ID: 20260404_0031
Revises: 20260329_0030
Create Date: 2026-04-04 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260404_0031"
down_revision = "20260329_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_oil_scenario_overlay_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("is_stale", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "snapshot_date",
            name="uq_company_oil_overlay_snapshots_company_date",
        ),
    )
    op.create_index(
        "ix_company_oil_overlay_snapshots_company",
        "company_oil_scenario_overlay_snapshots",
        ["company_id"],
    )
    op.create_index(
        "ix_company_oil_overlay_snapshots_company_date",
        "company_oil_scenario_overlay_snapshots",
        ["company_id", "snapshot_date"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_company_oil_overlay_snapshots_company_date",
        table_name="company_oil_scenario_overlay_snapshots",
    )
    op.drop_index(
        "ix_company_oil_overlay_snapshots_company",
        table_name="company_oil_scenario_overlay_snapshots",
    )
    op.drop_table("company_oil_scenario_overlay_snapshots")