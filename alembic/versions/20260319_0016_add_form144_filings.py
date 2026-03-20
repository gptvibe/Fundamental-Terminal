"""add form 144 filings table

Revision ID: 20260319_0016
Revises: 20260319_0015
Create Date: 2026-03-19 20:10:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260319_0016"
down_revision = "20260319_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "form144_filings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("accession_number", sa.String(length=32), nullable=False),
        sa.Column("form", sa.String(length=16), nullable=False),
        sa.Column("filing_date", sa.Date(), nullable=True),
        sa.Column("report_date", sa.Date(), nullable=True),
        sa.Column("transaction_index", sa.Integer(), nullable=False),
        sa.Column("filer_name", sa.String(length=255), nullable=True),
        sa.Column("relationship_to_issuer", sa.String(length=120), nullable=True),
        sa.Column("issuer_name", sa.String(length=255), nullable=True),
        sa.Column("security_title", sa.String(length=255), nullable=True),
        sa.Column("planned_sale_date", sa.Date(), nullable=True),
        sa.Column("shares_to_be_sold", sa.Float(), nullable=True),
        sa.Column("aggregate_market_value", sa.Float(), nullable=True),
        sa.Column("shares_owned_after_sale", sa.Float(), nullable=True),
        sa.Column("broker_name", sa.String(length=255), nullable=True),
        sa.Column("source_url", sa.String(length=500), nullable=False),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.Column("last_updated", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_checked", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "accession_number", "transaction_index", name="uq_form144_filings_company_accession_index"),
    )
    op.create_index("ix_form144_filings_company_id", "form144_filings", ["company_id"], unique=False)
    op.create_index("ix_form144_filings_company_filing_date", "form144_filings", ["company_id", "filing_date"], unique=False)
    op.create_index(
        "ix_form144_filings_company_planned_sale_date",
        "form144_filings",
        ["company_id", "planned_sale_date"],
        unique=False,
    )
    op.create_index("ix_form144_filings_company_last_checked", "form144_filings", ["company_id", "last_checked"], unique=False)

    op.add_column("companies", sa.Column("form144_filings_last_checked", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("companies", "form144_filings_last_checked")

    op.drop_index("ix_form144_filings_company_last_checked", table_name="form144_filings")
    op.drop_index("ix_form144_filings_company_planned_sale_date", table_name="form144_filings")
    op.drop_index("ix_form144_filings_company_filing_date", table_name="form144_filings")
    op.drop_index("ix_form144_filings_company_id", table_name="form144_filings")
    op.drop_table("form144_filings")
