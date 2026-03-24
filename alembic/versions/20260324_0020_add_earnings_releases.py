"""Add earnings releases cache tables

Revision ID: 20260324_0020
Revises: 20260323_0019
Create Date: 2026-03-24
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260324_0020"
down_revision = "20260323_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("earnings_last_checked", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "earnings_releases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("accession_number", sa.String(length=32), nullable=False),
        sa.Column("form", sa.String(length=16), nullable=False),
        sa.Column("filing_date", sa.Date(), nullable=True),
        sa.Column("report_date", sa.Date(), nullable=True),
        sa.Column("source_url", sa.String(length=500), nullable=False),
        sa.Column("primary_document", sa.String(length=255), nullable=True),
        sa.Column("exhibit_document", sa.String(length=255), nullable=True),
        sa.Column("exhibit_type", sa.String(length=32), nullable=True),
        sa.Column("reported_period_label", sa.String(length=120), nullable=True),
        sa.Column("reported_period_end", sa.Date(), nullable=True),
        sa.Column("revenue", sa.Float(), nullable=True),
        sa.Column("operating_income", sa.Float(), nullable=True),
        sa.Column("net_income", sa.Float(), nullable=True),
        sa.Column("diluted_eps", sa.Float(), nullable=True),
        sa.Column("revenue_guidance_low", sa.Float(), nullable=True),
        sa.Column("revenue_guidance_high", sa.Float(), nullable=True),
        sa.Column("eps_guidance_low", sa.Float(), nullable=True),
        sa.Column("eps_guidance_high", sa.Float(), nullable=True),
        sa.Column("share_repurchase_amount", sa.Float(), nullable=True),
        sa.Column("dividend_per_share", sa.Float(), nullable=True),
        sa.Column("highlights", postgresql.JSONB(), nullable=False),
        sa.Column("parse_state", sa.String(length=32), nullable=False),
        sa.Column("last_updated", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_checked", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "accession_number", name="uq_earnings_releases_company_accession"),
    )
    op.create_index("ix_earnings_releases_company_id", "earnings_releases", ["company_id"])
    op.create_index("ix_earnings_releases_company_filing_date", "earnings_releases", ["company_id", "filing_date"])
    op.create_index("ix_earnings_releases_company_report_date", "earnings_releases", ["company_id", "reported_period_end"])
    op.create_index("ix_earnings_releases_company_last_checked", "earnings_releases", ["company_id", "last_checked"])


def downgrade() -> None:
    op.drop_index("ix_earnings_releases_company_last_checked", table_name="earnings_releases")
    op.drop_index("ix_earnings_releases_company_report_date", table_name="earnings_releases")
    op.drop_index("ix_earnings_releases_company_filing_date", table_name="earnings_releases")
    op.drop_index("ix_earnings_releases_company_id", table_name="earnings_releases")
    op.drop_table("earnings_releases")
    op.drop_column("companies", "earnings_last_checked")
