"""add watchlist alerts

Revision ID: 20260510_0048
Revises: 20260506_0001
Create Date: 2026-05-10 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260510_0048"
down_revision = "20260506_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "watchlist_alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("alert_type", sa.String(length=32), nullable=False),
        sa.Column("source_filing_accession", sa.String(length=32), nullable=True),
        sa.Column("source_filing_form", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "alert_type",
            "source_filing_accession",
            name="uq_watchlist_alerts_company_type_accession",
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_watchlist_alerts_company_id", "watchlist_alerts", ["company_id"], unique=False)
    op.create_index("ix_watchlist_alerts_company_created", "watchlist_alerts", ["company_id", "created_at"], unique=False)
    op.create_index("ix_watchlist_alerts_company_type", "watchlist_alerts", ["company_id", "alert_type"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_watchlist_alerts_company_type", table_name="watchlist_alerts")
    op.drop_index("ix_watchlist_alerts_company_created", table_name="watchlist_alerts")
    op.drop_index("ix_watchlist_alerts_company_id", table_name="watchlist_alerts")
    op.drop_table("watchlist_alerts")
