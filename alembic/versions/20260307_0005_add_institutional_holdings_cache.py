"""add institutional holdings cache

Revision ID: 20260307_0005
Revises: 20260307_0004
Create Date: 2026-03-07 23:05:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260307_0005"
down_revision = "20260307_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("institutional_holdings_last_checked", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "institutional_funds",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("fund_cik", sa.String(length=20), nullable=False),
        sa.Column("fund_name", sa.String(length=255), nullable=False),
        sa.Column("fund_manager", sa.String(length=255), nullable=False),
        sa.Column("last_checked", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_updated", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_institutional_funds_fund_cik", "institutional_funds", ["fund_cik"], unique=True)
    op.create_index("ix_institutional_funds_fund_manager", "institutional_funds", ["fund_manager"], unique=False)

    op.create_table(
        "institutional_holdings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("fund_id", sa.Integer(), nullable=False),
        sa.Column("accession_number", sa.String(length=32), nullable=False),
        sa.Column("reporting_date", sa.Date(), nullable=False),
        sa.Column("filing_date", sa.Date(), nullable=True),
        sa.Column("shares_held", sa.Float(), nullable=True),
        sa.Column("market_value", sa.Float(), nullable=True),
        sa.Column("change_in_shares", sa.Float(), nullable=True),
        sa.Column("percent_change", sa.Float(), nullable=True),
        sa.Column("portfolio_weight", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=255), nullable=False),
        sa.Column("last_updated", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("last_checked", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["fund_id"], ["institutional_funds.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "fund_id",
            "reporting_date",
            name="uq_institutional_holdings_company_fund_reporting_date",
        ),
    )
    op.create_index("ix_institutional_holdings_company_id", "institutional_holdings", ["company_id"], unique=False)
    op.create_index("ix_institutional_holdings_fund_id", "institutional_holdings", ["fund_id"], unique=False)
    op.create_index(
        "ix_institutional_holdings_company_reporting_date",
        "institutional_holdings",
        ["company_id", "reporting_date"],
        unique=False,
    )
    op.create_index(
        "ix_institutional_holdings_company_last_checked",
        "institutional_holdings",
        ["company_id", "last_checked"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_institutional_holdings_company_last_checked", table_name="institutional_holdings")
    op.drop_index("ix_institutional_holdings_company_reporting_date", table_name="institutional_holdings")
    op.drop_index("ix_institutional_holdings_fund_id", table_name="institutional_holdings")
    op.drop_index("ix_institutional_holdings_company_id", table_name="institutional_holdings")
    op.drop_table("institutional_holdings")

    op.drop_index("ix_institutional_funds_fund_manager", table_name="institutional_funds")
    op.drop_index("ix_institutional_funds_fund_cik", table_name="institutional_funds")
    op.drop_table("institutional_funds")

    op.drop_column("companies", "institutional_holdings_last_checked")
